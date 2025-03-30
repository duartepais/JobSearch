"""
Collection of functions that help the main file and do not fit the model category
"""


def find_multiple_tags(soup, tag_name, tag_attrs, children_tag_names_list):
    """find the all tags given the different attribute possibilities"""

    if tag_attrs is None:
        first_results = soup.find_all(tag_name)

    elif "value" not in tag_attrs:
        first_results = soup.find_all(tag_name, {tag_attrs["key"]: True})

    else:
        first_results = soup.find_all(tag_name, {tag_attrs["key"]: tag_attrs["value"]})

    tags_it_must_contain = set(
        [child_tag for child_tag in children_tag_names_list if child_tag is not None]
    )

    final_results = [
        result
        for result in first_results
        if all(result.find(child_tag) for child_tag in tags_it_must_contain)
    ]

    return final_results


def find_single_tag(soup, tag_name, tag_attrs):
    """find the specific tag given the different attribute possibilities"""

    if tag_attrs is None:
        return soup.find(tag_name)

    if "value" not in tag_attrs:
        return soup.find(tag_name, {tag_attrs["key"]: True})

    return soup.find(tag_name, {tag_attrs["key"]: tag_attrs["value"]})
