"""
Classes for API interactions
"""

from abc import ABC, abstractmethod
from copy import deepcopy
from enum import Enum

import requests

from utils import clean_api_response, format_by_path

REQUEST_TIMEOUT = 5


class APIRequestType(Enum):
    """
    Enumeration for the different kinds of API requests
    """

    POST = "POST"
    GET = "GET"


class APIPaginationType(Enum):
    """
    Enumeration for the different locations of the API pagination
    """

    BODY = "body"
    HEADERS = "headers"
    URL = "url"


class APIInteraction(ABC):
    """
    Blueprint abstraction for API interactions
    """

    def __init__(self, info_dict: str):
        self.base_url = info_dict["base_url"]
        self.request_type = APIRequestType(info_dict["type"])

        self.request_headers = (
            info_dict["request"]["headers"]
            if "request" in info_dict and "headers" in info_dict["request"]
            else None
        )

        self.request_payload = (
            info_dict["request"]["body"]
            if "request" in info_dict and "body" in info_dict["request"]
            else None
        )

    @abstractmethod
    def fetch_response(self) -> str:
        """Get the response from this endpoint"""


class IterativeAPIInteraction(APIInteraction):
    """
    Abstraction for iterative API interactions
    """

    def __init__(self, info_dict):
        super().__init__(info_dict)

        self.pagination_type = APIPaginationType(info_dict["pagination"]["type"])
        self.pagination_location = info_dict["pagination"]["loc"]

        self.current_stage = info_dict["pagination"]["start_point"]
        self.increment = info_dict["pagination"]["increment"]

    def fetch_response(self) -> str:
        """Get the response from this endpoint"""

        request_url = self.base_url
        request_body = deepcopy(self.request_payload)
        request_headers = deepcopy(self.request_headers)

        match self.pagination_type:
            case APIPaginationType.URL:
                request_url = self.base_url.format(page_nr=self.current_stage)
            case APIPaginationType.BODY:
                request_body = format_by_path(
                    request_body,
                    self.pagination_location,
                    "page_nr",
                    self.current_stage,
                )
            case APIPaginationType.HEADERS:
                request_headers = format_by_path(
                    request_headers,
                    self.pagination_location,
                    "page_nr",
                    self.current_stage,
                )

        match self.request_type:
            case APIRequestType.GET:
                response = requests.get(
                    url=request_url,
                    headers=request_headers,
                    json=request_body,
                    timeout=REQUEST_TIMEOUT,
                )
            case APIRequestType.POST:
                response = requests.post(
                    url=request_url,
                    headers=request_headers,
                    json=request_body,
                    timeout=REQUEST_TIMEOUT,
                )

        return clean_api_response(response)

    def increase_stage_number(self):
        """Increase the current page number to fetch"""
        self.current_stage += self.increment


class SingleAPIInteraction(APIInteraction):
    """
    Abstraction for single API interactions
    """

    def fetch_response(self) -> str:
        """Get the response from this endpoint"""

        response = None

        match self.request_type:

            case APIRequestType.GET:
                response = requests.get(
                    url=self.base_url,
                    headers=self.request_headers,
                    json=self.request_payload,
                    timeout=REQUEST_TIMEOUT,
                )
            case APIRequestType.POST:
                response = requests.post(
                    url=self.base_url,
                    headers=self.request_headers,
                    json=self.request_payload,
                    timeout=REQUEST_TIMEOUT,
                )

        return clean_api_response(response)
