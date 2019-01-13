"""
Module for converting Catalog objects to and from dictionaries.

:copyright:
    The ObsPy Development Team (devs@obspy.org)
:license:
    GNU Lesser General Public License, Version 3
    (https://www.gnu.org/copyleft/lesser.html)
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)
from future.builtins import *  # NOQA

import copy

import obspy
import obspy.core.event as ev
from obspy.core.misc import _camel2snake
from obspy.core.util.obspy_types import Enum
from obspy.core.event.base import QuantityError

# attribute keys which are UTCDateTime instances
UTC_KEYS = ("creation_time", "time", "reference")

EVENT_ATTRS = ev.Event._containers + [x[0] for x in ev.Event._properties]


def catalog_to_dict(obj):
    """
    Recursively convert a event related objects to a dict.

    :type obj: Any object associated with Obspy's event hierarchy.
    :param obj: The object to be converted to a dictionary.

    :return: A dict.
    """
    # if this is a non-recursible type (ie a leaf) return it
    if isinstance(obj, (int, float, str)) or obj is None:
        return obj
    # if a sequence recurse each member
    elif isinstance(obj, (list, tuple)):
        if not len(obj):  # container is empty
            return obj
        else:
            return [catalog_to_dict(x) for x in obj]
    elif isinstance(obj, dict):  # if this is a dict recurse on each value
        return {key: catalog_to_dict(value) for key, value in obj.items()}
    else:  # else if this is an obspy class convert to dict
        return catalog_to_dict(_obj_to_dict(obj))


def dict_to_catalog(catalog_dict, inplace=False):
    """
    Create a catalog from a dictionary.

    :param catalog_dict: Catalog information in dictionary format.
    :type catalog_dict: dict.
    :param inplace:
        If True, modify catalog_dict in-place as objects are created, else
        deepcopy input dictionary before performing the conversion.
    :type inplace: bool

    :return: An ObsPy :class:`~obspy.core.event.Catalog` object.
    """
    assert isinstance(catalog_dict, dict)
    if not inplace:
        catalog_dict = copy.deepcopy(catalog_dict)
    return obspy.Catalog(**_parse_dict_class(catalog_dict))


def _get_params_from_docs(obj):
    """
    Attempt to figure out params for obj from the doc strings.
    """
    doc_list = obj.__doc__.splitlines()
    params_lines = [x for x in doc_list if ":param" in x]
    params = [x.split(":")[1].replace("param ", "") for x in params_lines]
    return params


def _getattr_factory(attributes):
    """
    Return a function that looks for attributes on an object and puts them
    into a dictionary. None will be returned if the object does not have any
    of the attributes.
    """

    def func(obj):
        out = {x: getattr(obj, x) for x in attributes if hasattr(obj, x)}
        return out or None  # return None rather than empty dict

    return func


def make_class_map():
    """
    Return a dict that maps names in QML to the appropriate obspy class.
    """

    # add "special" cases to mapping
    out = dict(mag_errors=QuantityError)
    out.update({x: obspy.UTCDateTime for x in UTC_KEYS})

    def _add_lower_and_plural(name, cls):
        """ add the lower case and plural case to dict"""
        name_lower = _camel2snake(name)
        name_plural = name_lower + "s"
        out[name_lower] = cls
        out[name_plural] = cls  # add both singular and plural

    # iterate all classes contained in core.event and add to dict
    for name, cls in ev.__dict__.items():
        if not isinstance(cls, type):
            continue
        if hasattr(cls, "_property_dict"):
            for name_, obj_type in cls._property_dict.items():
                # skip enums, object creation handles validation of these
                if isinstance(obj_type, Enum):
                    continue
                _add_lower_and_plural(name_, obj_type)
        _add_lower_and_plural(name, cls)
    return out


# a cache for functions that convert obspy objects to dictionaries
_OBSPY_TO_DICT_FUNCS = {obspy.UTCDateTime: lambda x: str(x),
                        ev.ResourceIdentifier: lambda x: str(x),
                        ev.Event: _getattr_factory(EVENT_ATTRS)}

# a cache for mapping attribute names to expected obspy classes
_OBSPY_CLASS_MAP = make_class_map()


def _obj_to_dict(obj):
    """
    Return the dict representation of object.

    Uses only public interfaces to in attempt to future-proof the
    serialization schemas.
    """
    try:
        return _OBSPY_TO_DICT_FUNCS[type(obj)](obj)
    except KeyError:
        params = _get_params_from_docs(obj)
        # create function for processing
        _OBSPY_TO_DICT_FUNCS[type(obj)] = _getattr_factory(params)
        # register function for future caching
        return _OBSPY_TO_DICT_FUNCS[type(obj)](obj)


def _parse_dict_class(input_dict):
    """
    Parse a dictionary, init expected obspy classes.
    """
    class_set = set(_OBSPY_CLASS_MAP)
    cdict_set = set(input_dict)
    # get set of keys that are obspy classes in the current dict
    class_keys = class_set & cdict_set
    # iterate over keys that are also classes and recurse when needed
    for key in class_keys:
        cls = _OBSPY_CLASS_MAP[key]
        val = input_dict[key]
        if val is None:
            continue
        if isinstance(val, list):
            input_dict[key] = [_init_update(x, cls) for x in val]
        elif isinstance(val, dict):  # use dict to init class
            input_dict[key] = _init_update(val, cls)
        # input should be only argument to class constructor
        else:
            input_dict[key] = cls(val)

    return input_dict


def _init_update(input_dict, cls):
    """
    init an object from cls and update its __dict__.
    """
    if not input_dict:
        return input_dict
    obj = cls(**_parse_dict_class(input_dict))
    # some objects instantiate even with None param, set back to None.
    # Maybe not an issue after  #2185?
    for attr in set(obj.__dict__) & set(input_dict):
        if input_dict[attr] is None:
            setattr(obj, attr, None)
    return obj
