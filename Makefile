#vars
REPO=nledez
IMAGENAME=drift_prom_exporter
TAG=$(or $(shell git describe --tags --abbrev=0 2>/dev/null | sed 's/^v//'),latest)
IMAGEFULLNAME=${REPO}/${IMAGENAME}:${TAG}
VENV=./venv

.PHONY: help build push all

help:
	    @echo "Makefile arguments:"
	    @echo ""
	    @echo "Makefile commands:"
	    @echo "build"
	    @echo "push"

.DEFAULT_GOAL := build

install:
	[ -d $(VENV) ] || virtualenv -p `command -v python3` $(VENV) && $(VENV)/bin/python -m pip install --upgrade pip
	$(VENV)/bin/pip install -r requirements.txt

run: install
	$(VENV)/bin/python main.py drift_prom_exporter.yml

curl:
	curl localhost:8000

docker_build:
	@docker build --pull -t ${IMAGEFULLNAME} .

docker_run:
	@docker container run --volume "`pwd`/drift_prom_exporter.yml:/drift_prom_exporter.yml" --env "CONFIG=/drift_prom_exporter.yml" --publish 8000:8000 ${IMAGEFULLNAME}

docker_push:
	@docker push ${IMAGEFULLNAME}
