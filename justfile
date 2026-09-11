# vars
REPO := "nledez"
IMAGENAME := "drift_prom_exporter"
TAG := `git describe --tags --abbrev=0 2>/dev/null | sed 's/^v//' || echo "latest"`
IMAGEFULLNAME := REPO + "/" + IMAGENAME + ":" + TAG
VENV := "./venv"

# default recipe
default: docker_build

help:
    just --list

install:
    uv sync

run: install
    uv run main.py drift_prom_exporter.yml

curl:
    curl http://127.0.0.1:${PORT}

docker_build:
    @docker build --pull -t {{ IMAGEFULLNAME }} .

docker_run:
    @docker container run --volume "`pwd`/drift_prom_exporter.yml:/drift_prom_exporter.yml" --env "CONFIG=/drift_prom_exporter.yml" --publish 8000:8000 {{ IMAGEFULLNAME }}

docker_push:
    @docker push {{ IMAGEFULLNAME }}

test:
    uv run --group dev pytest -v

# Increment version (patch/minor/major) and commit VERSION
bump part="patch":
    #!/usr/bin/env bash
    set -euo pipefail
    IFS='.' read -r major minor patch < VERSION
    case "{{ part }}" in
        patch) patch=$((patch + 1)) ;;
        minor) minor=$((minor + 1)); patch=0 ;;
        major) major=$((major + 1)); minor=0; patch=0 ;;
        *) echo "Unknown part: {{ part }} (use patch, minor or major)"; exit 1 ;;
    esac
    new_version="${major}.${minor}.${patch}"
    echo "$new_version" > VERSION
    git add VERSION
    git commit -m "Bump version to v${new_version}"
    echo "Version bumped to v${new_version}, run 'just release' to tag and push"

# Tag the current VERSION and propose to push commits and tag
release:
    #!/usr/bin/env bash
    set -euo pipefail
    version="$(tr -d '[:space:]' < VERSION)"
    if [[ -z "$version" ]]; then
        echo "VERSION is empty"; exit 1
    fi
    tag="v${version}"
    if ! git diff --quiet || ! git diff --cached --quiet; then
        echo "Uncommitted changes, commit or stash before releasing"; exit 1
    fi
    if git rev-parse -q --verify "refs/tags/${tag}" >/dev/null; then
        echo "Tag ${tag} already exists"; exit 1
    fi
    git tag -a "${tag}" -m "Release ${tag}"
    echo "Tagged ${tag}"
    read -p "Push commits and ${tag} to origin? [y/N] " answer
    if [[ "$answer" =~ ^[yY]$ ]]; then
        git push
        git push origin "${tag}"
    else
        echo "Not pushed. Run 'git push && git push origin ${tag}' when ready,"
        echo "or 'git tag -d ${tag}' to drop the tag."
    fi
