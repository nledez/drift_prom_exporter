# vars
REPO := "nledez"
IMAGENAME := "drift_prom_exporter"
TAG := `git describe --tags --abbrev=0 2>/dev/null | sed 's/^v//' || echo "latest"`
IMAGEFULLNAME := REPO + "/" + IMAGENAME + ":" + TAG
VENV := "./venv"

# default recipe
default: build

help:
    @echo "justfile commands:"
    @echo ""
    @echo "build"
    @echo "push"

install:
    [ -d {{ VENV }} ] || virtualenv -p `command -v python3` {{ VENV }} && {{ VENV }}/bin/python -m pip install --upgrade pip
    {{ VENV }}/bin/pip install -r requirements.txt

run: install
    {{ VENV }}/bin/python main.py drift_prom_exporter.yml

curl:
    curl localhost:8000

docker_build:
    @docker build --pull -t {{ IMAGEFULLNAME }} .

docker_run:
    @docker container run --volume "`pwd`/drift_prom_exporter.yml:/drift_prom_exporter.yml" --env "CONFIG=/drift_prom_exporter.yml" --publish 8000:8000 {{ IMAGEFULLNAME }}

docker_push:
    @docker push {{ IMAGEFULLNAME }}
