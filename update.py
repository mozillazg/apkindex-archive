#!/usr/bin/python
import json
import os.path
import pathlib
import shutil
import tempfile
import urllib.request
from collections import defaultdict

import bs4
from urllib.parse import urljoin
import logging
import tarfile
import git


formatter = "%(asctime)s %(levelname)s : %(message)s"
logging.basicConfig(level=logging.DEBUG, format=formatter)
logger = logging.getLogger("apkindex-archive")

base_url = "http://dl-cdn.alpinelinux.org/alpine/"


def main():
    if not has_update():
        logger.info("no update")
        return
    parse_root(base_url)
    commit()


def has_update():
    url = urljoin(base_url, "last-updated")
    last_updated = urllib.request.urlopen(url).read()
    last_updated = int(last_updated)
    with open("last-updated", "r") as f:
        current = int(f.read())

    if int(current) < last_updated:
        return True
    return False


def last_update():
    url = urljoin(base_url, "last-updated")
    last_updated = urllib.request.urlopen(url).read()
    last_updated = int(last_updated)
    with open("last-updated", "w") as f:
        f.write(str(last_updated))


def parse_root(url: str):
    logger.info(url)
    soup = bs4.BeautifulSoup(
        urllib.request.urlopen(base_url).read(), features="html.parser"
    )
    for a in soup.find_all("a"):
        v = a.get("href")
        if not v.startswith("v"):
            continue
        parse_version_page(urljoin(url, v))


def parse_version_page(url: str):
    soup = bs4.BeautifulSoup(urllib.request.urlopen(url).read(), features="html.parser")
    for a in soup.find_all("a"):
        repo = a.get("href")
        if repo not in ["main/", "community/"]:
            continue
        parse_repo_page(urljoin(url, repo))


def parse_repo_page(url: str):
    soup = bs4.BeautifulSoup(urllib.request.urlopen(url).read(), features="html.parser")
    for a in soup.find_all("a"):
        arch = a.get("href")
        if arch == "../":
            continue
        parse_arch_page(urljoin(url, arch))


def parse_arch_page(url: str):
    soup = bs4.BeautifulSoup(urllib.request.urlopen(url).read(), features="html.parser")
    for a in soup.find_all("a"):
        file = a.get("href")
        if file != "APKINDEX.tar.gz":
            continue
        download_apkindex(urljoin(url, file))


def download_apkindex(url: str):
    logger.info(url)

    url_obj = urllib.parse.urlparse(url)
    dir, base = os.path.split(url_obj.path)

    with tempfile.TemporaryDirectory() as dname:
        logger.info(dname)
        file_path = os.path.join(dname, base)
        urllib.request.urlretrieve(url, file_path)
        with tarfile.open(file_path, "r:*") as tar:
            tar.extractall(dname)

        file_name = base.replace(".tar.gz", "")
        dst_dir = dir[1:]
        pathlib.Path(dst_dir).mkdir(parents=True, exist_ok=True)
        shutil.move(os.path.join(dname, file_name), os.path.join(dst_dir, file_name))
        parse_apkindex(dst_dir, file_name)


def parse_apkindex(dir: str, file_name: str):
    nested = lambda: defaultdict(nested)
    hook = lambda d: defaultdict(nested, d)

    file_path = os.path.join(dir, "history.json")
    current = nested()
    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            current = json.load(f, object_hook=hook)

    with open(os.path.join(dir, file_name), "r") as f:
        for line in f:
            line = line.strip()
            if line.startswith("P:"):
                pkg = line[2:]
            elif line.startswith("V:"):
                version = line[2:]
            elif line.startswith("t:"):
                time = int(line[2:])
            elif line == "":
                current[pkg][version] = time

    logger.info("update history.json")
    with open(os.path.join(dir, "history.json"), "w") as f:
        json.dump(current, f, indent=2)


def commit():
    repo = git.cmd.Git()
    result = repo.status("--porcelain")
    if len(result) == 0:
        return
    last_update()
    repo.add("last-updated")
    repo.add("alpine/")
    repo.commit(message="Automatic update")
    repo.push("origin", "master")


if __name__ == "__main__":
    main()
