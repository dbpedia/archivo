from typing import Tuple
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests

from archivo.utils import archivoConfig


def check_robot_allowed(uri: str) -> Tuple[bool, str]:
    parsed_url = urlparse(uri)

    robots_url = str(parsed_url.scheme) + "://" + str(parsed_url.netloc) + "/robots.txt"
    try:
        req = requests.get(url=robots_url)
    except Exception as e:
        return True, str(e)

    if req.status_code > 400:
        # if robots.txt is not accessible, we are allowed
        return True, "OK"
    rp = RobotFileParser()
    rp.set_url(robots_url)
    rp.parse(req.text.split("\n"))
    if rp.can_fetch(archivoConfig.archivo_agent, uri):
        return True, None
    else:
        return False, "Not allowed"
