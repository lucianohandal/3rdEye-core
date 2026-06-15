.PHONY: test coverage coverage-html

PYTHON ?= .venv/bin/python
TEST_CMD = -m unittest discover -s tests -p '*.py' -t . -v

test:
	$(PYTHON) $(TEST_CMD)

coverage:
	$(PYTHON) -m coverage run $(TEST_CMD)
	$(PYTHON) -m coverage report -m

coverage-html:
	$(PYTHON) -m coverage run $(TEST_CMD)
	$(PYTHON) -m coverage html
	$(PYTHON) -m coverage report -m
