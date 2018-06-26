import logging.config
import math
import os
import time

import requests

from .autohash import AutoHash

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


API_KEY = os.environ["MEETUP_API_KEY"]
base_url = "https://api.meetup.com"
endpoints = {
    "members": (f"{base_url}/" + "{group}/members").format,
    "events":  (f"{base_url}/" + "{group}/events").format,
}


class MeetupRequest:

    api_key = API_KEY
    page_size = 100

    @staticmethod
    def _throttle(resp):
        rate_limit_limit = int(resp.headers["X-RateLimit-Limit"])
        rate_limit_remaining = int(resp.headers["X-RateLimit-Remaining"])
        rate_limit_reset = int(resp.headers["X-RateLimit-Reset"])
        if rate_limit_remaining <= 0:
            time.sleep(rate_limit_reset + 1)

    @classmethod
    def _calculate_total_pages(cls, resp):
        total_count = int(resp.headers["X-Total-Count"])
        total_pages = math.ceil(total_count / cls.page_size)
        return total_pages

    @staticmethod
    def _rate_limited(resp):
        return resp.status_code ==  429

    @classmethod
    def _get(cls, url, params):
        logger.debug(f"GET {url} with {params}")
        offset = 0
        max_offset = 0

        params.update({
            "key": cls.api_key,
            "page": cls.page_size,
            "offset": offset,
        })

        while offset <= max_offset:
            logger.debug(f"Getting offset {offset}")

            params.update({
                "offset": offset,
            })
            resp = requests.get(url, params=params)

            logger.debug(f"Got resp.status_code {resp.status_code}")

            max_offset = cls._calculate_total_pages(resp)

            if not cls._rate_limited(resp):
                yield resp
                offset += 1

            cls._throttle(resp)

    @classmethod
    def get(cls, url, params=None):
        request_params = {
            "key": cls.api_key,
            "page": cls.page_size,
            "offset": 0,
        }
        if isinstance(params, dict):
            request_params.update(params)
        responses = list(cls._get(url, request_params))

        return responses

    @classmethod
    def _unique(cls, items):
        unique = set()
        def _is_new(event):
            if AutoHash(event["id"]) in unique:
                return False
            else:
                unique.add(AutoHash(event["id"]))
                return True
        items = [
            item
            for item in items
            if _is_new(item)
        ]
        return items

    @classmethod
    def members(cls, group):
        responses = MeetupRequest.get(endpoints["members"](group=group))
        members = cls._unique(
            member
            for r in responses
            for member in r.json()
        )
        return members

    @classmethod
    def events(cls, group):
        responses = MeetupRequest.get(
            endpoints["events"](group=group),
            params={"status": "past"}
        )
        events = cls._unique(
            event
            for r in responses
            for event in r.json()
        )
        return events


class Group:
    def __init__(self, name):
        self.name = name

    @property
    def members(self):
        if not hasattr(self, "_members"):
            self._members = MeetupRequest.members(self.name)
        return self._members

    @property
    def events(self):
        if not hasattr(self, "_events"):
            self._events = MeetupRequest.events(self.name)
        return self._events
