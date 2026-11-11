"""Safe YAML, additionally rejecting duplicate mapping keys."""

import yaml

from contractgate.models import Contract


class UniqueKeyLoader(yaml.SafeLoader):
    pass


def unique_mapping(loader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as error:
            raise ValueError("contract mapping keys must be scalar") from error
        if duplicate:
            raise ValueError(f"duplicate YAML key: {key}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def load_contract(text: str) -> Contract:
    if len(text) > 64000:
        raise ValueError("contract exceeds 64,000 characters")
    return Contract.model_validate(yaml.load(text, Loader=UniqueKeyLoader))
