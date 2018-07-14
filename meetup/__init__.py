import logging.config
import math
import os
import textwrap
import time

import requests

from .autohash import AutoHash
from.memoized_property import memoized_property

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


API_KEY = os.environ["MEETUP_API_KEY"]
base_url = "https://api.meetup.com"
endpoints = {
    "group": (f"{base_url}/" + "{group}").format,
    "group/members": (f"{base_url}/" + "{group}/members").format,
    "group/events":  (f"{base_url}/" + "{group}/events").format,
    "group/find":  (f"{base_url}/" + "find/groups").format,
    "member": (f"{base_url}/" + "members/{member_id}").format
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
            wait_time = rate_limit_reset + 1
            logger.info(textwrap.dedent("""
                Api RateLimit reached waiting {}
                    limit: {}
                    remaining: {}
                    reset: {}
            """).format(wait_time,
                        rate_limit_limit,
                        rate_limit_remaining,
                        rate_limit_reset))
            time.sleep(wait_time)

    @classmethod
    def _calculate_total_pages(cls, resp):
        total_count = int(resp.headers.get("X-Total-Count", "0"))
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
        def _is_new(item):
            if AutoHash(item["id"]) in unique:
                return False
            else:
                unique.add(AutoHash(item["id"]))
                return True
        items = [
            item
            for item in items
            if _is_new(item)
        ]
        return items

    @classmethod
    def coords(cls, group):
        responses = MeetupRequest.get(
            endpoints["group"](group=group),
            params = {
                "only": "lat,lon"
            }
        )
        return responses[0].json()

    @classmethod
    def members(cls, group):
        responses = MeetupRequest.get(endpoints["group/members"](group=group))
        members = cls._unique(
            member
            for r in responses
            for member in r.json()
        )
        return members

    @classmethod
    def events(cls, group):
        responses = MeetupRequest.get(
            endpoints["group/events"](group=group),
            params={"status": "past"}
        )
        events = cls._unique(
            event
            for r in responses
            for event in r.json()
        )
        return events

    @classmethod
    def memberships(cls, member_id):
        responses = MeetupRequest.get(
            endpoints["member"](member_id=member_id),
            params = {
                "fields": "memberships",
                "only": "memberships"
            }
        )
        memberships = responses[0].json().get("memberships", {})
        organizer = memberships.get("organizer", [])
        member = memberships.get("member", [])
        return organizer + member

    @classmethod
    def find_groups(cls, lat, lon, radius):
        # assert 0 < radius < 100
        responses = MeetupRequest.get(
            endpoints["group/find"](),
            params = {
                "lat": lat,
                "lon": lon,
                "radius": radius,
            }
        )
        groups = cls._unique(
            group
            for r in responses
            for group in r.json()
        )
        return groups


class Group:
    def __init__(self, name, _coords=None):
        self.name = name
        if _coords is not None:
            self._coords = _coords


    # TODO
    # @property
    # def info(self):
    #     pass
    @property
    def lat(self):
        if not hasattr(self, "_coords"):
            self._coords = MeetupRequest.coords(self.name)
        return self._coords["lat"]

    @property
    def lon(self):
        if not hasattr(self, "_coords"):
            self._coords = MeetupRequest.coords(self.name)
        return self._coords["lon"]

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


class Groups:
    @classmethod
    def find(cls, lat, lon, radius):
        return  [
            Group(
                name=group["urlname"],
                _coords=dict(
                    lat=group["lat"],
                    lon=group["lon"],
                )
            )
            for group in MeetupRequest.find_groups(lat=lat, lon=lon,
                                                   radius=radius)
        ]


class Member:
    def __init__(self, member_id):
        self._member_id = member_id

    @memoized_property
    def memberships(self):
        return MeetupRequest.memberships(self._member_id)
