import requests
from datetime import datetime
import locales
import utils
import os
import settingsTools
from pathlib import Path
settings = settingsTools.loadSettings()

locales = locales.Locales()


class Version(object):
    def __init__(self, content):
        lines = content.splitlines()
        self.version = lines[0].replace("\n", "")
        self.branch = lines[1].replace("\n", "") if len(lines) >= 2 else None
        self.commit_hash = lines[2].replace("\n", "") if len(lines) >= 3 and lines[2].replace("\n", "") != "" else None
        self.version_file = None

    def write_commit_hash(self, hash):
        if self.version_file is not None:
            with open(self.version_file) as fr:
                lines = fr.readlines()
            if len(lines) >= 3:
                lines[2] = f"{hash}\n"
            else:
                lines.append(f"{hash}\n")
            with open(self.version_file, "w") as fw:
                fw.writelines(lines)


    @classmethod
    def get_version_file(cls):
        for file in Path(".").rglob("version.txt"):
            strpath = str(file)
            with open(strpath) as f:
                cls = cls(f.read())
                cls.version_file = strpath
                return cls

class Repository(object):
    # TODO: implement set_cache
    def __init__(self, name):
        self.name = name
        self.cache = {}

    def get_download_url(self, branch, path):
        return f"https://raw.githubusercontent.com/{self.name}/{branch}/{path}"

    @property
    def repository_name(self):
        return self.name.split("/")[1]

    def get_tree(self, branch) -> dict:
        tmp_tree = {}
        r = requests.get(f"https://api.github.com/repos/{self.name}/git/trees/{branch}?recursive=true").json()
        self.__verify_request(r)
        for i in r["tree"]:
            tmp_tree[i["path"]] = i["type"]
        return tmp_tree

    def compare_tree(self, branch):
        tree = self.get_tree(branch)
        for file, type in tree.items():
            if not os.path.exists(file):
                if type == "tree":
                    os.makedirs(file)
                else:
                    locales.advPrint("FILE_IS_MISSING", globals={"file": file})
                    utils.downloadFileWithBar(self.get_download_url(branch, file), file)

    def get_cache(self, *args):
        last_arg = None
        for counter, i in enumerate(args):
            getres = self.cache.get(i) if last_arg is None else last_arg.get(i)
            if type(getres) != dict or counter == len(args) - 1:
                return getres
            else:
                last_arg = getres

    def get_commit_info(self, commit):
        commit_info = requests.get(f"https://api.github.com/repos/{self.name}/commits/{commit}").json()
        self.__verify_request(commit_info)
        return commit_info

    def get_branches(self):
        tmp_branches = {}
        branches = requests.get(f"https://api.github.com/repos/{self.name}/branches").json()
        self.__verify_request(branches)
        self.cache["branches"] = {}
        for branch in branches:
            commit = branch["commit"]["sha"]
            commit_info = self.get_commit_info(commit)
            commit_datetime = datetime.strptime(commit_info["commit"]["author"]["date"], "%Y-%m-%dT%H:%M:%S%z").replace(
                tzinfo=None)
            delta = datetime.now() - commit_datetime
            tmp_branches[
                f"{branch['name']} [{locales.message('DAYS_AGO', {'days': delta.days})}]"] = commit_info
            self.cache["branches"][branch['name']] = commit_info
        return tmp_branches

    def get_version(self, branch):
        return Version(requests.get(f"https://raw.githubusercontent.com/{self.name}/{branch}/version.txt").text)

    def get_latest_commit_hash(self, branch):
        if (cacheres := self.get_cache("branches", branch)) is None:
            r = requests.get(f"https://api.github.com/repos/{self.name}/branches/{branch}").json()
            self.__verify_request(r)
            return r["commit"]["sha"]
        else:
            return cacheres["sha"]

    def clone(self, branch):
        version = self.get_version(branch).version
        expected_path = f"{self.repository_name} {version}"
        utils.downloadFileAndExtract(f"https://github.com/{self.name}/archive/{branch}.zip",
                                     f"{branch}.zip")
        if os.path.exists(expected_path):
            utils.rmtree(expected_path)
        os.rename(f"{self.repository_name}-{branch}", expected_path)

    def diff_commits(self, base, head):
        r = requests.get(f"https://api.github.com/repos/{self.name}/compare/{base}...{head}").json()
        self.__verify_request(r)
        show_commits = settings["show_last_X_commits"]
        locales.advPrint("COMMIT_DIFF_RESULTS", globals={"ahead_commits": r["ahead_by"], "last_count": show_commits})
        for commit in r["commits"][-show_commits::]:
            print(f"[+] {commit['commit']['message']}")


    def __verify_request(self, r):
        if type(r) == dict and r.get("message") is not None:
            raise Exception(r.get("message"))