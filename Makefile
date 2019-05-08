check-full: check
	pylint \
	  --max-line-length=120 \
	  *.py tests/*.py
	yamllint -c .yamllint.strict .travis.yml data/*.yaml

check:
	yamllint data/*.yaml .travis.yml
	flake8 *.py tests/*.py
	pylint \
	  --max-line-length=120 \
	  --disable=missing-docstring,fixme,invalid-name,too-few-public-methods,global-statement,too-many-locals \
	  *.py tests/*.py
	mypy *.py tests/*.py
	coverage run --branch --module unittest discover tests
	coverage report --show-missing --fail-under=100

server:
	@echo 'Open <http://localhost:8000/osm> in your browser.'
	uwsgi --plugins http,python3 --http :8000 --wsgi-file wsgi.py
