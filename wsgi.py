#!/usr/bin/env python3
#
# Copyright 2019 Miklos Vajna. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#

"""The wsgi module contains functionality specific to the web interface."""

import configparser
import datetime
import locale
import os
import traceback
import urllib.parse
import json
import subprocess
import wsgiref.simple_server

import pytz

import helpers
import overpass_query
import version


def get_config():
    """Gets access to information which are specific to this installation."""
    config = configparser.ConfigParser()
    config_path = os.path.join(os.path.dirname(__file__), "wsgi.ini")
    config.read(config_path)
    if not config.has_option("wsgi", "workdir"):
        workdir = os.path.join(os.path.dirname(__file__), "workdir")
        if not os.path.exists(workdir):
            os.makedirs(workdir)
        config.set("wsgi", "workdir", workdir)
    return config


def get_datadir():
    """Gets the directory which is tracked (in version control) data."""
    return os.path.join(os.path.dirname(__file__), "data")


def get_staticdir():
    """Gets the directory which is static data."""
    return os.path.join(os.path.dirname(__file__), "static")


def handle_streets(request_uri, workdir, relations):
    """Expected request_uri: e.g. /osm/streets/ormezo/view-query."""
    output = ""

    tokens = request_uri.split("/")
    relation = tokens[-2]
    action = tokens[-1]

    if action == "view-query":
        output += "<pre>"
        output += helpers.get_streets_query(get_datadir(), relations, relation)
        output += "</pre>"
    elif action == "view-result":
        with open(os.path.join(workdir, "streets-%s.csv" % relation)) as sock:
            table = helpers.tsv_to_list(sock)
            output += helpers.html_table_from_list(table)
    elif action == "update-result":
        query = helpers.get_streets_query(get_datadir(), relations, relation)
        helpers.write_streets_result(workdir, relation, overpass_query.overpass_query(query))
        output += "Frissítés sikeres."

    osmrelation = relations[relation]["osmrelation"]
    date = get_streets_last_modified(workdir, relation)
    return get_header("streets", relation, osmrelation) + output + get_footer(date)


def handle_street_housenumbers(request_uri, workdir, relations):
    """Expected request_uri: e.g. /osm/street-housenumbers/ormezo/view-query."""
    output = ""

    tokens = request_uri.split("/")
    relation = tokens[-2]
    action = tokens[-1]

    if action == "view-query":
        output += "<pre>"
        output += helpers.get_street_housenumbers_query(get_datadir(), relations, relation)
        output += "</pre>"
    elif action == "view-result":
        with open(os.path.join(workdir, "street-housenumbers-%s.csv" % relation)) as sock:
            table = helpers.tsv_to_list(sock)
            output += helpers.html_table_from_list(table)
    elif action == "update-result":
        query = helpers.get_street_housenumbers_query(get_datadir(), relations, relation)
        helpers.write_street_housenumbers(workdir, relation, overpass_query.overpass_query(query))
        output += "Frissítés sikeres."

    osmrelation = relations[relation]["osmrelation"]
    date = get_housenumbers_last_modified(workdir, relation)
    return get_header("street-housenumbers", relation, osmrelation) + output + get_footer(date)


def suspicious_streets_view_result(request_uri, workdir):
    """Expected request_uri: e.g. /osm/suspicious-streets/ormezo/view-result."""
    tokens = request_uri.split("/")
    relation = tokens[-2]

    output = ""
    if not os.path.exists(os.path.join(workdir, "streets-" + relation + ".csv")):
        output += "Nincsenek meglévő utcák: "
        output += "<a href=\"/osm/streets/" + relation + "/update-result\">"
        output += "Létrehozás Overpass hívásával</a>"
    elif not os.path.exists(os.path.join(workdir, "street-housenumbers-" + relation + ".csv")):
        output += "Nincsenek meglévő házszámok: "
        output += "<a href=\"/osm/street-housenumbers/" + relation + "/update-result\">"
        output += "Létrehozás Overpass hívásával</a>"
    elif not os.path.exists(os.path.join(workdir, "street-housenumbers-reference-" + relation + ".lst")):
        output += "Nincsenek hiányzó házszámok: "
        output += "<a href=\"/osm/suspicious-streets/" + relation + "/update-result\">"
        output += "Létrehozás referenciából</a>"
    else:
        ret = helpers.write_suspicious_streets_result(get_datadir(), workdir, relation)
        todo_street_count, todo_count, done_count, percent, table = ret

        output += "<p>Elképzelhető, hogy az OpenStreetMap nem tartalmazza a lenti "
        output += str(todo_street_count) + " utcához tartozó "
        output += str(todo_count) + " házszámot."
        output += " (meglévő: " + str(done_count) + ", készültség: " + str(percent) + "%).<br>"
        output += "<a href=\"" + \
                  "https://github.com/vmiklos/osm-gimmisn/tree/master/doc/hu" + \
                  "#hib%C3%A1s-riaszt%C3%A1s-hozz%C3%A1ad%C3%A1sa\">" + \
                  "Téves információ jelentése</a>.</p>"

        output += helpers.html_table_from_list(table)
    return output


def suspicious_streets_view_txt(request_uri, workdir):
    """Expected request_uri: e.g. /osm/suspicious-streets/ormezo/view-result.txt."""
    tokens = request_uri.split("/")
    relation = tokens[-2]

    output = ""
    if not os.path.exists(os.path.join(workdir, "streets-" + relation + ".csv")):
        output += "Nincsenek meglévő utcák"
    elif not os.path.exists(os.path.join(workdir, "street-housenumbers-" + relation + ".csv")):
        output += "Nincsenek meglévő házszámok"
    elif not os.path.exists(os.path.join(workdir, "street-housenumbers-reference-" + relation + ".lst")):
        output += "Nincsenek referencia házszámok"
    else:
        suspicious_streets, _ = helpers.get_suspicious_streets(get_datadir(), workdir, relation)
        table = []
        for result in suspicious_streets:
            if result[1]:
                # House number, only_in_reference items.
                row = result[0] + "\t[" + ", ".join(result[1]) + "]"
                table.append(row)
        table.sort(key=locale.strxfrm)
        output += "\n".join(table)
    return output


def suspicious_streets_update(workdir, relation):
    """Expected request_uri: e.g. /osm/suspicious-streets/ormezo/update-result."""
    datadir = get_datadir()
    reference = get_config().get('wsgi', 'reference_local').strip()
    helpers.get_reference_housenumbers(reference, datadir, workdir, relation)
    return "Frissítés sikeres."


def handle_suspicious_streets(request_uri, workdir, relations):
    """Expected request_uri: e.g. /osm/suspicious-streets/ormezo/view-[result|query]."""
    output = ""

    tokens = request_uri.split("/")
    relation = tokens[-2]
    action = tokens[-1]
    action_noext, _, ext = action.partition('.')

    if action_noext == "view-result":
        if ext == "txt":
            return suspicious_streets_view_txt(request_uri, workdir)

        output += suspicious_streets_view_result(request_uri, workdir)
    elif action_noext == "view-query":
        output += "<pre>"
        path = "street-housenumbers-reference-%s.lst" % relation
        with open(os.path.join(workdir, path)) as sock:
            output += sock.read()
        output += "</pre>"
    elif action_noext == "update-result":
        output += suspicious_streets_update(workdir, relation)

    osmrelation = relations[relation]["osmrelation"]
    date = ref_housenumbers_last_modified(workdir, relation)
    return get_header("suspicious-streets", relation, osmrelation) + output + get_footer(date)


def local_to_ui_tz(local_dt):
    """Converts from local date-time to UI date-time, based on config."""
    config = get_config()
    if config.has_option("wsgi", "timezone"):
        ui_tz = pytz.timezone(config.get("wsgi", "timezone"))
    else:
        ui_tz = pytz.timezone("Europe/Budapest")

    return local_dt.astimezone(ui_tz)


def get_last_modified(workdir, path):
    """Gets the update date of a file in workdir."""
    return format_timestamp(get_timestamp(workdir, path))


def get_timestamp(workdir, path):
    """Gets the timestamp of a file in workdir."""
    try:
        return os.path.getmtime(os.path.join(workdir, path))
    except FileNotFoundError:
        return 0


def format_timestamp(timestamp):
    """Formats timestamp as UI date-time."""
    local_dt = datetime.datetime.fromtimestamp(timestamp)
    ui_dt = local_to_ui_tz(local_dt)
    fmt = '%Y-%m-%d %H:%M'
    return ui_dt.strftime(fmt)


def ref_housenumbers_last_modified(workdir, name):
    """Gets the update date for suspicious streets."""
    t_ref = get_timestamp(workdir, "street-housenumbers-reference-" + name + ".lst")
    t_housenumbers = get_timestamp(workdir, "street-housenumbers-" + name + ".csv")
    return format_timestamp(max(t_ref, t_housenumbers))


def get_housenumbers_last_modified(workdir, name):
    """Gets the update date of house numbers for a relation."""
    return get_last_modified(workdir, "street-housenumbers-" + name + ".csv")


def get_streets_last_modified(workdir, name):
    """Gets the update date of streets for a relation."""
    return get_last_modified(workdir, "streets-" + name + ".csv")


def handle_main(relations, workdir):
    """Handles the main wsgi page."""
    output = ""

    output += "<h1>Hol térképezzek?</h1>"
    table = []
    table.append(["Terület", "Házszám lefedettség", "Meglévő házszámok", "Meglévő utcák", "Terület határa"])
    for k in sorted(relations):
        relation = relations[k]
        row = []
        row.append(k)
        percent_file = k + ".percent"
        url = "\"/osm/suspicious-streets/" + k + "/view-result\""
        percent = "N/A"
        if os.path.exists(os.path.join(workdir, percent_file)):
            percent = helpers.get_content(workdir, percent_file)

        if percent != "N/A":
            date = get_last_modified(workdir, percent_file)
            cell = "<strong><a href=" + url + " title=\"frissítve " + date + "\">"
            cell += percent + "%"
            cell += "</a></strong>"
            row.append(cell)
        else:
            cell = "<strong><a href=" + url + ">"
            cell += "hiányzó házszámok"
            cell += "</a></strong>"
            row.append(cell)

        date = get_housenumbers_last_modified(workdir, k)
        row.append("<a href=\"/osm/street-housenumbers/" + k + "/view-result\""
                   "title=\"frissítve " + date + "\" >meglévő házszámok</a>")

        date = get_streets_last_modified(workdir, k)
        row.append("<a href=\"/osm/streets/" + k + "/view-result\""
                   "title=\"frissítve " + date + "\" >meglévő utcák</a>")

        row.append("<a href=\"https://www.openstreetmap.org/relation/" + str(relation["osmrelation"])
                   + "\">terület határa</a>")

        table.append(row)
    output += helpers.html_table_from_list(table)
    output += "<a href=\"" + \
              "https://github.com/vmiklos/osm-gimmisn/tree/master/doc/hu" + \
              "#%C3%BAj-rel%C3%A1ci%C3%B3-hozz%C3%A1ad%C3%A1sa\">" + \
              "Új terület hozzáadása</a>"

    return get_header() + output + get_footer()


def get_header(function=None, relation_name=None, relation_osmid=None):
    """Produces the start of the page. Note that the contnt depends on the function and the
    relation, but not on the action to keep a balance between too generic and too specific
    content."""
    title = ""
    items = []

    items.append("<a href=\"/osm\">Területek listája</a>")
    if relation_name:
        suspicious = '<a href="/osm/suspicious-streets/' + relation_name + '/view-result">Hiányzó házszámok</a>'
        suspicious += ' (<a href="/osm/suspicious-streets/' + relation_name + '/view-result.txt">txt</a>)'
        items.append(suspicious)
        items.append("<a href=\"/osm/street-housenumbers/" + relation_name + "/view-result\">Meglévő házszámok</a>")
        items.append("<a href=\"/osm/streets/" + relation_name + "/view-result\">Meglévő utcák</a>")

    if function == "suspicious-streets":
        title = " - " + relation_name + " hiányzó házszámok"
        items.append("<a href=\"/osm/suspicious-streets/" + relation_name + "/update-result\">"
                     + "Frissítés referenciából</a> (másodpercekig tarthat)")
    elif function == "street-housenumbers":
        title = " - " + relation_name + " meglévő házszámok"
        items.append("<a href=\"/osm/street-housenumbers/" + relation_name + "/update-result\">"
                     + "Frissítés Overpass hívásával</a> (másodpercekig tarthat)")
        items.append("<a href=\"/osm/street-housenumbers/" + relation_name + "/view-query\">"
                     + "Lekérdezés megtekintése</a>")
    elif function == "streets":
        title = " - " + relation_name + " meglévő utcák"
        items.append("<a href=\"/osm/streets/" + relation_name + "/update-result\">"
                     + "Frissítés Overpass hívásával</a> (másodpercekig tarthat)")
        items.append("<a href=\"/osm/streets/" + relation_name + "/view-query\">Lekérdezés megtekintése</a>")

    if relation_osmid:
        items.append("<a href=\"https://www.openstreetmap.org/relation/" + str(relation_osmid) + "\">"
                     + "Terület határa</a>")
    items.append("<a href=\"https://github.com/vmiklos/osm-gimmisn/tree/master/doc/hu\">Dokumentáció</a>")

    output = "<html><head><title>Hol térképezzek?" + title + "</title>"
    output += '<script src="/osm/static/sorttable.js"></script>'
    output += "</head><body><div>"
    output += " &brvbar; ".join(items)
    output += "</div><hr/>"
    return output


def get_footer(last_updated=None):
    """Produces the end of the page."""
    items = []
    items.append("Verzió: " + helpers.git_link(version.VERSION, "https://github.com/vmiklos/osm-gimmisn/commit/"))
    items.append("OSM adatok © OpenStreetMap közreműködők.")
    if last_updated:
        items.append("Utolsó frissítés: " + last_updated)
    output = "<hr/><div>"
    output += " &brvbar; ".join(items)
    output += "</div>"
    output += "</body></html>"
    return output


def handle_github_webhook(environ):
    """Handles a GitHub style webhook."""

    body = urllib.parse.parse_qs(environ["wsgi.input"].read().decode('utf-8'))
    payload = body["payload"][0]
    root = json.loads(payload)
    if root["ref"] == "refs/heads/master":
        subprocess.run(["make", "-C", version.GIT_DIR, "deploy-pythonanywhere"], check=True)

    return ""


def handle_static(request_uri):
    """Handles serving static content."""
    tokens = request_uri.split("/")
    path = tokens[-1]

    if path.endswith(".js"):
        return helpers.get_content(get_staticdir(), path)

    return ""


def our_application(environ, start_response):
    """Dispatches the request based on its URI."""
    config = get_config()
    if config.has_option("wsgi", "locale"):
        ui_locale = config.get("wsgi", "locale")
    else:
        ui_locale = "hu_HU.UTF-8"
    locale.setlocale(locale.LC_ALL, ui_locale)

    status = '200 OK'

    request_uri = environ.get("PATH_INFO")
    _, _, ext = request_uri.partition('.')

    config = get_config()

    workdir = helpers.get_workdir(config)

    relations = helpers.get_relations(get_datadir())

    content_type = "text/html"
    if ext == "txt":
        content_type = "text/plain"

    if request_uri.startswith("/osm/streets/"):
        output = handle_streets(request_uri, workdir, relations)
    elif request_uri.startswith("/osm/street-housenumbers/"):
        output = handle_street_housenumbers(request_uri, workdir, relations)
    elif request_uri.startswith("/osm/suspicious-streets/"):
        output = handle_suspicious_streets(request_uri, workdir, relations)
    elif request_uri.startswith("/osm/webhooks/github"):
        output = handle_github_webhook(environ)
    elif request_uri.startswith("/osm/static/"):
        output = handle_static(request_uri)
        if request_uri.endswith(".js"):
            content_type = "application/x-javascript"
    else:
        output = handle_main(relations, workdir)

    output_bytes = output.encode('utf-8')
    response_headers = [('Content-type', content_type + '; charset=utf-8'),
                        ('Content-Length', str(len(output_bytes)))]
    start_response(status, response_headers)
    return [output_bytes]


def handle_exception(environ, start_response):
    """Displays an unhandled exception on the page."""
    status = '500 Internal Server Error'
    request_uri = environ.get("PATH_INFO")
    body = "<pre>Internal error when serving " + request_uri + "\n" + \
           traceback.format_exc() + "</pre>"
    output = get_header() + body + get_footer()
    output_bytes = output.encode('utf-8')
    response_headers = [('Content-type', 'text/html; charset=utf-8'),
                        ('Content-Length', str(len(output_bytes)))]
    start_response(status, response_headers)
    return [output_bytes]


def application(environ, start_response):
    """The entry point of this WSGI app."""
    try:
        return our_application(environ, start_response)

    # pylint: disable=broad-except
    except Exception:
        return handle_exception(environ, start_response)


def main():
    """Commandline interface to this module."""
    httpd = wsgiref.simple_server.make_server('', 8000, application)
    print("Open <http://localhost:8000/osm> in your browser.")
    httpd.serve_forever()


if __name__ == "__main__":
    main()

# vim:set shiftwidth=4 softtabstop=4 expandtab:
