"""
Classes for companies' websites and job listings
"""

import re
import traceback

from enum import auto, Enum

from bs4 import BeautifulSoup
from bs4.element import Tag

from dotenv import dotenv_values

from models.browser import (
    SimplePageInteraction,
    LoadMoreInteraction,
    PaginationInteraction,
)
from utils import find_multiple_tags, find_single_tag

config = dotenv_values(".env")


class ResultsLoading(Enum):
    """
    Enumeration for the different kinds of results loading
    """

    PAGINATION = auto()
    LOAD_MORE_SAME_PAGE = auto()
    SIMPLE_SAME_PAGE = auto()


class Company:
    """
    Abstraction for the company website and its scraping
    """

    def __init__(self, company_dict: dict):
        self.name = company_dict["name"]
        self.url = company_dict["base_url"]
        self.results_loading = self.get_results_loading_type(company_dict)
        self.job_container_metadata = JobContainerMetadata(
            company_dict["job_container"]
        )
        self.jobs_dict = {}
        self.errors = []

    def get_results_loading_type(self, company_dict: dict):
        """Assess which kind of results loading this website has"""

        if "next_page" in company_dict:
            self.browser_interaction = PaginationInteraction(
                self.url, company_dict["next_page"], company_dict["job_container"]
            )
            return ResultsLoading.PAGINATION
        elif "load_more" in company_dict:
            self.browser_interaction = LoadMoreInteraction(
                self.url, company_dict["load_more"], company_dict["job_container"]
            )
            return ResultsLoading.LOAD_MORE_SAME_PAGE
        else:
            self.browser_interaction = SimplePageInteraction(self.url)
            return ResultsLoading.SIMPLE_SAME_PAGE

    def fetch_results(self):
        """Get all the job results available in a company's website"""

        try:
            self.browser_interaction.run()
        except Exception as error:
            self.errors.append(" ".join(error.args))
        else:
            match self.results_loading:
                case ResultsLoading.PAGINATION:
                    html_list = self.browser_interaction.html_list
                case (
                    ResultsLoading.LOAD_MORE_SAME_PAGE | ResultsLoading.SIMPLE_SAME_PAGE
                ):
                    html_list = [self.browser_interaction.html]

            job_containers = []

            for html in html_list:
                job_containers.extend(self.extract_jobs_from_html(html))

            ids_set = set([job.id for job in job_containers])
            refined_ids_set = set([job.refined_id for job in job_containers])

            if len(refined_ids_set) != len(ids_set):
                self.errors.append(
                    f"Something wrong with the id refinement of the company {self.name}"
                )

                self.jobs_dict = {job.id: job.title for job in job_containers}
            else:
                self.jobs_dict = {job.refined_id: job.title for job in job_containers}

            if not self.jobs_dict:
                self.errors.append(
                    f"No results were retrieved; check the website of {self.name}"
                )

    def extract_jobs_from_html(self, html: str):
        """Get the appropriate job info from the raw html"""

        page_soup = BeautifulSoup(html, features="html.parser")

        job_container_soups = find_multiple_tags(
            page_soup,
            self.job_container_metadata.main_tag,
            self.job_container_metadata.main_tag_attrs,
            [self.job_container_metadata.title_tag, self.job_container_metadata.id_tag],
        )

        job_containers = []

        for job_soup in job_container_soups:
            try:
                job_containers.append(
                    JobContainer(self.job_container_metadata, job_soup)
                )
            except (ValueError, AttributeError):
                continue
            except Exception:
                self.errors.append(traceback.format_exc())

        return job_containers


class JobContainerMetadata:
    """
    Abstraction containing the important html tags associated with a job container
    """

    def __init__(self, info_dict: dict):
        self.main_tag = info_dict["tag"]
        self.main_tag_attrs = None if "attrs" not in info_dict else info_dict["attrs"]

        if "title_tag" not in info_dict:
            self.title_tag, self.title_tag_attrs = None, None
        else:
            self.title_tag = info_dict["title_tag"]["tag"]
            self.title_tag_attrs = (
                None
                if "attrs" not in info_dict["title_tag"]
                else info_dict["title_tag"]["attrs"]
            )

        if "id_tag" not in info_dict:
            self.id_tag, self.id_tag_attrs, self.id_tag_attr_location, self.id_regex = (
                None,
                None,
                None,
                None,
            )
        else:

            self.id_tag = (
                None if "tag" not in info_dict["id_tag"] else info_dict["id_tag"]["tag"]
            )

            self.id_tag_attrs = (
                None
                if "attrs" not in info_dict["id_tag"]
                else info_dict["id_tag"]["attrs"]
            )

            self.id_tag_attr_location = info_dict["id_tag"]["attr_location"]

            self.id_regex = (
                None
                if "regex" not in info_dict["id_tag"]
                else info_dict["id_tag"]["regex"]
            )


class JobContainer:
    """
    Abstraction containing the selected info of a job container
    """

    def __init__(self, container_metadata: JobContainerMetadata, container_soup: Tag):

        self.metadata = container_metadata
        self.title = self.get_title(container_soup)
        self.id = self.get_id(container_soup)
        self.refined_id = self.refined_id()

    def get_title(self, soup: Tag):
        """
        Fetch job title from soup object
        Input: container soup object
        Output: processed string with job title
        """

        if self.metadata.title_tag is None:
            title_raw_string = soup.text
        else:
            title_soup = find_single_tag(
                soup, self.metadata.title_tag, self.metadata.title_tag_attrs
            )

            title_raw_string = title_soup.text

        title_processed_string = " ".join(
            title_raw_string.replace("\xa0", " ").splitlines()
        ).strip()

        if not title_processed_string:
            raise ValueError(
                "This soup object has an empty text content for the title attribute"
            )

        return title_processed_string

    def get_id(self, soup: Tag):
        """
        Fetch id from soup object, if available
        Input: container soup object
        Output: if available, job id, else, job title
        """

        if self.metadata.id_tag:
            id_soup = find_single_tag(
                soup, self.metadata.id_tag, self.metadata.id_tag_attrs
            )

            id_string = id_soup.attrs[self.metadata.id_tag_attr_location].strip()

        elif self.metadata.id_tag_attr_location:
            id_string = soup.attrs[self.metadata.id_tag_attr_location].strip()

        else:
            id_string = self.title.strip()

        if not id_string:
            raise ValueError(
                "This soup object has an empty text content for the id attribute"
            )

        return id_string

    def refined_id(self):
        """
        Fetch the refined id from the raw id value, if available
        Output: if available, refined job id, else, raw job id
        """

        if self.metadata.id_regex:
            return re.search(self.metadata.id_regex, self.id).group(1)
        else:
            return self.id

    def to_dict(self):
        """
        Get a representable dict of the job
        """

        return {self.refined_id: self.title}
