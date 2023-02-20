from typing import List

import requests


class WebDAVException(Exception):
    """Generalized exception for WebDAV requests"""

    def __init__(self, resp: requests.Response):
        super().__init__(
            f"Exception during WebDAV Request {resp.request.method} to "
            f"{resp.request.url}: Status {resp.status_code}\nResponse: {resp.text}"
        )


class WebDAVHandler:
    """Work with a WebDAV endpoint."""

    def __init__(self, dav_base: str, api_key: str):
        """DAV Base"""
        self.dav_base = dav_base
        self.api_key = api_key

    def check_existence(self, path: str) -> bool:
        """check if path is available"""
        try:
            resp = requests.head(url=f"{self.dav_base}{path}", timeout=4)
        except requests.RequestException:
            return False

        return bool(resp.status_code == 405)

    def create_dir(
            self, path: str, session: requests.Session = None
    ) -> requests.Response:
        """create directory"""

        if session is None:
            session = requests.Session()

        req = requests.Request(
            method="MKCOL",
            url=f"{self.dav_base}{path}",
            headers={"X-API-KEY": f"{self.api_key}"},
        )
        resp = session.send(req.prepare())
        return resp

    def create_dirs(self, path: str) -> List[requests.Response]:
        """create directories"""

        dirs = path.split("/")
        responses = []
        current_path = ""
        for directory in dirs:
            current_path = current_path + directory + "/"
            if not self.check_existence(current_path):
                resp = self.create_dir(current_path)
                responses.append(resp)
                # 200 and 201 means creation worked, 405 means it was already there
                if resp.status_code not in [200, 201, 405]:
                    raise WebDAVException(resp)

        return responses

    def upload_file(
            self, path: str, data: bytes, create_parent_dirs: bool = False
    ) -> requests.Response:
        """upload data in bytes to a path, optionally creating parent dirs."""

        if create_parent_dirs:
            dirpath = path.rsplit("/", 1)[0]
            self.create_dirs(dirpath)

        resp = requests.put(  # pylint: disable=missing-timeout
            url=f"{self.dav_base}{path}",
            headers={"X-API-KEY": f"{self.api_key}"},
            data=data,
        )

        return resp
