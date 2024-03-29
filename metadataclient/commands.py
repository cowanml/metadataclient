import requests
import datetime
import pytz
import six
from functools import wraps
import ujson
from metadataclient import (conf, utils)

"""
.. warning:: This is very early alpha. The skeleton is here but not all full blown features are implemented here
.. warning: The client lives in the service for now. I will move it to separate repo once ready for alpha release
"""

# TODO: Add capability that run_start can either be a document or string
# TODO: Add server_disconnect that rolls all config back to default
# TODO: Add capped collection caching layer for the client
# TODO: Add fast read/write capped collection, different than caching capped collection
# TODO: Add timeouts to servers in order to stop ppl from abusing data sources
# TODO: Add callback capability on monitors

def server_connect(host, port, protocol='http'):
    """The server here refers the metadataservice server itself, not the mongo server
    .. note:: Do not gasp yet! I copied w/e mongoengine did for global connectionpool management.

    Parameters
    ----------
    host: str
        name/address of the mongo server
    port: int
        port number of mongo server
    protocol: str, optional
        in case we want to introduce ssl in the future. for now, eliminates possible ambiguities

     Returns
    -------
    _server_path: str
        Full server path that is set globally. Useful for monkeypatching
        overwrites config and updates this global server path
    """
    global _server_path
    _server_path = protocol + '://' + host + ':' + str(port)
    return _server_path

def server_disconnect():
    raise NotImplementedError('Coming soon...')

def _ensure_connection(func):
    """Ensures connection to the tornado server, not mongo instance itself.
    Essentially, re-using what we have done for the library but this time for tornado backend
    instead of mongodb daemon
    """
    @wraps(func)
    def inner(*args, **kwargs):
        protocol = conf.connection_config['protocol']
        host = conf.connection_config['host']
        port = conf.connection_config['port']
        server_connect(host=host, port=port, protocol=protocol)
        return func(*args, **kwargs)
    return inner


def doc_or_uid_to_uid(doc_or_uid):
    """Given Document or uid return the uid

    Parameters
    ----------
    doc_or_uid : dict or str
        If str, then assume uid and pass through, if not, return
        the 'uid' field

    Returns
    -------
    uid : str
        A string version of the uid of the given document

    """
    if not isinstance(doc_or_uid, six.string_types):
        doc_or_uid = doc_or_uid['uid']
    return doc_or_uid


@_ensure_connection
def runstart_given_uid(uid):
    """Get RunStart document given an ObjectId
    This is an internal function as ObjectIds should not be
    leaking out to user code.
    When we migrate to using uid as the primary key this function
    will be removed. Server strips the ObjectId fields for the client
    Parameters
    ----------
    uid : str
        Unique identifier for the document.
    Returns
    -------
    run_start : doc.Document
        The RunStart document.
    """
    # TODO: Add capped collection caching lookup
    return next(find_run_starts(uid=uid)) #already returns document


@_ensure_connection
def _run_start_given_oid(oid):
    """Get RunStart document given an ObjectId

    This is an internal function as ObjectIds should not be
    leaking out to user code.

    When we migrate to using uid as the primary key this function
    will be removed.

    Parameters
    ----------
    oid : ObjectId
        Mongo's unique identifier for the document.  This is currently
        used to implement foreign keys

    Returns
    -------
    run_start : utils.Document
        The RunStart document.
    """
    return utils.Document('RunStart', next(find_run_starts(_id=oid)))


@_ensure_connection
def _descriptor_given_oid(oid):
    """Get EventDescriptor document given an ObjectId

    This is an internal function as ObjectIds should not be
    leaking out to user code.

    When we migrate to using uid as the primary key this function
    will be removed.

    Parameters
    ----------
    oid : ObjectId
        Mongo's unique identifier for the document.  This is currently
        used to implement foreign keys

    Returns
    -------
    descriptor : doc.Document
        The EventDescriptor document.
    """
    #runstart replaced in server side
    descriptor = dict(next(find_descriptors(oid=oid)))
    return utils.Document('EventDescriptor', descriptor)


@_ensure_connection
def runstop_given_uid(uid):
    """Given a uid, return the RunStop document

    Parameters
    ----------
    uid : str
        The uid

    Returns
    -------
    run_stop : utils.Document
        The RunStop document fully de-referenced

    """
    run_stop = dict(next(find_run_stops(uid=uid)))
    start_oid = run_stop.pop('run_start_id')
    run_stop['run_start'] = _run_start_given_oid(start_oid)
    return utils.Document('RunStop', run_stop)


@_ensure_connection
def run_start_given_uid(uid):
    """Given a uid, return the RunStart document

    Parameters
    ----------
    uid : str
        The uid

    Returns
    -------
    run_start : utils.Document
        The RunStart document.

    """
    return utils.Document('RunStart', next(find_run_starts(uid=uid)))


@_ensure_connection
def run_stop_given_uid(uid):
    """Given a uid, return the RunStop document

    Parameters
    ----------
    uid : str
        The uid

    Returns
    -------
    run_stop : utils.Document
        The RunStop document fully de-referenced

    """
    runstop = dict(next(find_run_stops(uid=uid)))
    start_oid = runstop.pop('run_start_id')
    runstop['run_start'] = _run_start_given_oid(start_oid)
    return utils.Document('RunStop', runstop)


@_ensure_connection
def descriptor_given_uid(uid):
    """Given a uid, return the EventDescriptor document

    Parameters
    ----------
    uid : str
        The uid

    Returns
    -------
    descriptor : utils.Document
        The EventDescriptor document fully de-referenced
    """
    descriptor = dict(next(find_descriptors(uid=uid)))
    start_oid = descriptor.pop('run_start_id')
    descriptor['run_start'] = _run_start_given_oid(start_oid)
    return utils.Document('EventDescriptor', descriptor)


@_ensure_connection
def stop_by_start(run_start):
    """Given a RunStart return it's RunStop
    Raises if no RunStop exists.

    Parameters
    ----------
    run_start : doc.Document or dict or str
        The RunStart to get the RunStop for.  Can be either
        a Document/dict with a 'uid' key or a uid string

    Returns
    -------
    run_stop : utils.Document
        The RunStop document

    Raises
    ------
    NoRunStop
        If no RunStop document exists for the given RunStart
    """
    
#     run_start_uid = doc_or_uid_to_uid(run_start)
#     rstart = run_start_given_uid(run_start.uid)
#     if rstart:
    run_stop = next(find_run_stops(run_start=run_start.uid))
#         run_stop['run_start'] = run_start
    return utils.Document('RunStop', run_stop)
#     else:
#         raise utils.NoRunStop()


@_ensure_connection
def descriptors_by_start(run_start):
    """Given a RunStart return a list of it's descriptors

    Raises if no EventDescriptors exist.

    Parameters
    ----------
    run_start : utils.Document or dict or str
        The RunStart to get the EventDescriptors for.  Can be either
        a Document/dict with a 'uid' key or a uid string

    Returns
    -------
    event_descriptors : list
        A list of EventDescriptor documents

    Raises
    ------
    NoEventDescriptors
        If no EventDescriptor documents exist for the given RunStart
    """
#     run_start_uid = doc_or_uid_to_uid(run_start)
#     run_start_given_uid(run_start_uid)
#     descriptors = find_descriptors(run_start=runs
    raise NotImplementedError()

@_ensure_connection
def fetch_events_generator(descriptor):
    """A generator which yields all events from the event stream

    Parameters
    ----------
    descriptor : doc.Document or dict or str
        The EventDescriptor to get the Events for.  Can be either
        a Document/dict with a 'uid' key or a uid string

    Yields
    ------
    event : utils.Document
        All events for the given EventDescriptor from oldest to
        newest
    """
    desc = descriptor_given_uid(descriptor.uid)
    raw_ev_gen = find_events(descriptor_id=str(desc['_id']))
    for ev in raw_ev_gen:
        ev.pop('descriptor_id')
        ev['descriptor'] = dict(desc)
        yield utils.Document('Event', ev)


def _transpose(in_data, keys, field):
    """Turn a list of dicts into dict of lists

    Parameters
    ----------
    in_data : list
        A list of dicts which contain at least one dict.
        All of the inner dicts must have at least the keys
        in `keys`

    keys : list
        The list of keys to extract

    field : str
        The field in the outer dict to use

    Returns
    -------
    transpose : dict
        The transpose of the data
    """
    out = {k: [None] * len(in_data) for k in keys}
    for j, ev in enumerate(in_data):
        dd = ev[field]
        for k in keys:
            out[k][j] = dd[k]
    return out


@_ensure_connection
def fetch_events_table(descriptor):
    """All event data as tables

    Parameters
    ----------
    descriptor : dict or str
        The EventDescriptor to get the Events for.  Can be either
        a Document/dict with a 'uid' key or a uid string

    Returns
    -------
    descriptor : doc.Document
        EventDescriptor document
    data_table : dict
        dict of lists of the transposed data
    seq_nums : list
        The sequence number of each event.
    times : list
        The time of each event.
    uids : list
        The uid of each event.
    timestamps_table : dict
        The timestamps of each of the measurements as dict of lists.  Same
        keys as `data_table`.
    """
    pass

@_ensure_connection
def find_run_starts(range_floor=0, range_ceil=50, **kwargs):
    """Given search criteria, locate RunStart Documents.
    As we describe in design document, time here is strictly the time
    server entry was created, not IOC timestamp. For the difference, refer
    to: nsls-ii.github.io
    Parameters
    ----------
    start_time : time-like, optional
        time-like representation of the earliest time that a RunStart
        was created. Valid options are:
           - timestamps --> time.time()
           - '2015'
           - '2015-01'
           - '2015-01-30'
           - '2015-03-30 03:00:00'
           - datetime.datetime.now()
    stop_time : time-like, optional
        timestamp of the latest time that a RunStart was created. See
        docs for `start_time` for examples.
    `beamline_id : str, optional
        String identifier for a specific beamline
    project : str, optional
        Project name
    owner : str, optional
        The username of the logged-in user when the scan was performed
    scan_id : int, optional
        Integer scan identifier
    uid : str, optional
        Globally unique id string provided to metadatastore
    _id : str or ObjectId, optional
        The unique id generated by mongo

    Returns
    -------
    content : iterable of list of json documents
        We need lists to be able to JSON encode multiple dicts. We can return an iterator of
         iterator?

    Note
    ----
    All documents that the RunStart Document points to are dereferenced.
    These include RunStop, BeamlineConfig, and Sample.

    Examples
    --------
    >>> find_run_starts(scan_id=123)
    >>> find_run_starts(owner='arkilic')
    >>> find_run_starts(start_time=1421176750.514707, stop_time=time.time()})
    >>> find_run_starts(start_time=1421176750.514707, stop_time=time.time())
    >>> find_run_starts(owner='arkilic', start_time=1421176750.514707,
    ...                stop_time=time.time())
    """
    _format_time(kwargs)
    query = kwargs
    increment = range_ceil - range_floor + 1
    has_more = True
    while has_more:
        q_range = range_ceil - range_floor
        query['range_floor'] = range_floor
        query['range_ceil'] = range_ceil
        r = requests.get(_server_path + "/run_start",
                         params=ujson.dumps(query))
        r.raise_for_status()
        content = ujson.loads(r.text)
        if not content:
            StopIteration()
            break
        else:
            for c in content:
                yield utils.Document('RunStart',c)
            if len(content) <= q_range:
                has_more = False
                break
            else:
                range_ceil += increment
                range_floor += increment


@_ensure_connection
def find_run_stops(run_start=None, range_floor=0, range_ceil=50, **kwargs):
    """Given search criteria, query for RunStop Documents.
    Parameters
    ----------
    run_start : metadatastore.document.Document or str, optional
        The metadatastore run start document or the metadatastore uid to get
        the corresponding run end for
    start_time : time-like, optional
        time-like representation of the earliest time that a RunStop
        was created. Valid options are:
           - timestamps --> time.time()
           - '2015'
           - '2015-01'
           - '2015-01-30'
           - '2015-03-30 03:00:00'
           - datetime.datetime.now()
    stop_time : time-like, optional
        timestamp of the latest time that a RunStop was created. See
        docs for `start_time` for examples.
    exit_status : {'success', 'fail', 'abort'}, optional
        provides information regarding the run success.
    reason : str, optional
        Long-form description of why the run was terminated.
    uid : str, optional
        Globally unique id string provided to metadatastore
    _id : str or ObjectId, optional
        The unique id generated by mongo

    Returns
    -------
    content : iterable of list of json documents
        We need lists to be able to JSON encode multiple dicts. We can return an iterator of
         iterator?
    """
    _format_time(kwargs)
    query = kwargs
    increment = range_ceil - range_floor + 1
    has_more = True
    if run_start:
        try:
            query['run_start'] = run_start.uid
        except AttributeError:
            query['run_start'] = str(run_start)
    while has_more:
        q_range = range_ceil - range_floor
        query['range_floor'] = range_floor
        query['range_ceil'] = range_ceil
        r = requests.get(_server_path + "/run_stop",
                         params=ujson.dumps(query))
        r.raise_for_status()
        content = ujson.loads(r.text)
        if not content:
            StopIteration()
            break
        else:
            for c in content:
                yield utils.Document('RunStop',c)
            if len(content) <= q_range:
                has_more = False
                break
            else:
                range_ceil += increment
                range_floor += increment


@_ensure_connection
def find_events(descriptor=None, range_floor=0, range_ceil=1000, **kwargs):
    """
    Parameters
    -----------
    start_time : time-like, optional
        time-like representation of the earliest time that an Event
        was created. Valid options are:
           - timestamps --> time.time()
           - '2015'
           - '2015-01'
           - '2015-01-30'
           - '2015-03-30 03:00:00'
           - datetime.datetime.now()
    stop_time : time-like, optional
        timestamp of the latest time that an Event was created. See
        docs for `start_time` for examples.
    descriptor : doc.Document or str, optional
       Find events for a given EventDescriptor
    uid : str, optional
        Globally unique id string provided to metadatastore
    Returns
    -------
    events : iterable of utils.Document objects
    """
    if 'event_descriptor' in kwargs:
        raise ValueError("Use 'descriptor', not 'event_descriptor'.")
    query = kwargs
    increment = range_ceil - range_floor + 1
    if descriptor:
        #TODO: Try to get from capped collection/cache instead of db hit
        descriptor = descriptor_given_uid(descriptor)
        query['descriptor_id'] = descriptor._id
    _format_time(kwargs)        
    has_more = True
    while has_more:
        q_range = range_ceil - range_floor
        query['range_floor'] = range_floor
        query['range_ceil'] = range_ceil
        r = requests.get(_server_path + "/run_stop",
                         params=ujson.dumps(query))
        r.raise_for_status()
        content = ujson.loads(r.text)
        if not content:
            StopIteration()
            break
        else:
            for c in content:
                desc_id = c.pop('descriptor_id')
                if descriptor:
                    c['descriptor'] = descriptor
                else:
                    # if descriptor not provided, find and replace
                    # primarily for event based search to succeed
                    # should not be used
                    descriptor = next(find_descriptors(_id=desc_id))
                yield utils.Document('Event',c)
            if len(content) <= q_range:
                has_more = False
                break
            else:
                range_ceil += increment
                range_floor += increment


@_ensure_connection
def find_descriptors(run_start=None, range_floor=0, range_ceil=50, **kwargs):
    """Given search criteria, locate EventDescriptor Documents.

    Parameters
    ----------
    run_start : metadatastore.document.Document or uid, optional
        The metadatastore run start document or the metadatastore uid to get
        the corresponding run end for
    run_start_uid : str
        Globally unique id string provided to metadatastore for the
        RunStart Document.
    start_time : time-like, optional
        time-like representation of the earliest time that an EventDescriptor
        was created. Valid options are:
           - timestamps --> time.time()
           - '2015'
           - '2015-01'
           - '2015-01-30'
           - '2015-03-30 03:00:00'
           - datetime.datetime.now()
    stop_time : time-like, optional
        timestamp of the latest time that an EventDescriptor was created. See
        docs for `start_time` for examples.
    uid : str, optional
        Globally unique id string provided to metadatastore
    _id : str or ObjectId, optional
        The unique id generated by mongo

    Returns
    -------
    content : iterable of list of json documents
        We need lists to be able to JSON encode multiple dicts. We can return an iterator of
         iterator?
    """
    _format_time(kwargs)
    query = kwargs
    increment = range_ceil - range_floor + 1
    has_more = True
    try:
        query['run_start'] = run_start.uid
    except AttributeError:
        query['run_start'] = str(run_start)
    while has_more:
        q_range = range_ceil - range_floor
        query['range_floor'] = range_floor
        query['range_ceil'] = range_ceil
        r = requests.get(_server_path + "/event_descriptor",
                         params=ujson.dumps(query))
        r.raise_for_status()
        content = ujson.loads(r.text)
        if not content:
            StopIteration()
            break
        else:
            for c in content:
                yield utils.Document('EventDescriptor',c)
            if len(content) <= q_range:
                has_more = False
                break
            else:
                range_ceil += increment
                range_floor += increment


@_ensure_connection
def insert_event(descriptor,events):
    "Insert a list of events. Server handles this in bulk"
    for ev in list(events):
        ev.pop('descriptor')
        try:
            ev['descriptor'] = descriptor.uid
        except AttributeError:
            ev['run_start'] = str(descriptor)
    ev = ujson.dumps(list(events))
    r = requests.post(_server_path + '/event', data=ev)
    return r


@_ensure_connection
def insert_descriptor(run_start, data_keys, time, uid=None,
                      custom=None):
    """ Create an event_descriptor in metadatastore server backend

    Parameters
    ----------
    run_start : metadatastore.documents.Document or str
        if Document:
            The metadatastore RunStart document
        if str:
            uid of RunStart object to associate with this record
    data_keys : dict
        Provides information about keys of the data dictionary in
        an event will contain
    time : float
        The date/time as found at the client side when an event
        descriptor is created.
    uid : str, optional
        Globally unique id string provided to metadatastore
    custom : dict, optional
        Any additional information that data acquisition code/user wants
        to append to the EventDescriptor.

    Returns
    -------
    ev_desc : EventDescriptor
        The document added to the collection.

    """
    payload = locals()
    tmp = payload['run_start'].uid
    payload.pop('run_start')
    payload['run_start'] = tmp
    r = requests.post(_server_path + '/event_descriptor', 
                      data=ujson.dumps(payload))
    if r.status_code != 200:
        raise Exception("Server cannot complete the request", r)
    else:
        return utils.Document('EventDescriptor', dict(r.json()))


@_ensure_connection
def insert_run_start(time, scan_id, config, beamline_id, beamline_config={}, uid=None,
                    owner=None, group=None, project=None, custom=None):
    """Provide a head for a sequence of events. Entry point for an
    experiment's run.

    Parameters
    ----------
    time : float
        The date/time as found at the client side when an event is
        created.
    scan_id : int
        Unique scan identifier visible to the user and data analysis
    beamline_id : str
        Beamline String identifier. Not unique, just an indicator of
        beamline code for multiple beamline systems
    beamline_config : metadatastore.documents.Document or str
        if Document:
            The metadatastore beamline config document
        if str:
            uid of beamline config corresponding to a given run
    uid : str, optional
        Globally unique id string provided to metadatastore
    owner : str, optional
        A username associated with the entry
    group : str, optional
        A group (e.g., UNIX group) associated with the entry
    project : str, optional
        Any project name to help users locate the data
    custom: dict, optional
        Any additional information that data acquisition code/user wants
        to append to the Header at the start of the run.
        
    Returns
    ----------
    utils.Document
        The run_start document that is successfully saved in mongo

    """
    data = locals()
    if custom:
        data.update(custom)
    payload = ujson.dumps(data)
    r = requests.post(_server_path + '/run_start', data=payload)
    if r.status_code != 200:
        raise Exception("Server cannot complete the request", r)
    else:
        return utils.Document('RunStart',r.json())


@_ensure_connection
def insert_run_stop(run_start, time, uid=None, config={}, exit_status='success',
                    reason=None, custom=None):
    """ Provide an end to a sequence of events. Exit point for an
    experiment's run.

    Parameters
    ----------
    run_start : metadatastore.documents.Document or str
        if Document:
            The metadatastore RunStart document
        if str:
            uid of RunStart object to associate with this record
    time : float
        The date/time as found at the client side when an event is
        created.
    uid : str, optional
        Globally unique id string provided to metadatastore
    exit_status : {'success', 'abort', 'fail'}, optional
        indicating reason run stopped, 'success' by default
    reason : str, optional
        more detailed exit status (stack trace, user remark, etc.)
    custom : dict, optional
        Any additional information that data acquisition code/user wants
        to append to the Header at the end of the run.

    Returns
    -------
    run_stop : mongoengine.Document
        Inserted mongoengine object
    """
    params = locals()
    rs_obj = params.pop('run_start')
    try:
        params['run_start'] = rs_obj.uid
    except AttributeError:
        params['run_start'] = rs_obj
    payload = ujson.dumps(params)
    r = requests.post(_server_path + '/run_stop', data=payload)
    if r.status_code != 200:
        raise Exception("Server cannot complete the request", r)
    else:
        return utils.Document('RunStop', r.json())


@_ensure_connection
def format_events():
    pass


def format_data_keys():
    pass


def _format_time(search_dict):
    """Helper function to format the time arguments in a search dict

    Expects 'start_time' and 'stop_time'

    ..warning: Does in-place mutation of the search_dict
    """
    time_dict = {}
    start_time = search_dict.pop('start_time', None)
    stop_time = search_dict.pop('stop_time', None)
    if start_time:
        time_dict['$gte'] = _normalize_human_friendly_time(start_time)
    if stop_time:
        time_dict['$lte'] = _normalize_human_friendly_time(stop_time)
    if time_dict:
        search_dict['time'] = time_dict


def find_last(range=1):
    pass

def monitor_run_start():
    r = requests.get(_server_path + '/run_start_capped')
    content = ujson.loads(r.text)
    yield utils.Document('RunStart', content)


def _insert2cappedstart(time, scan_id, config, beamline_id, beamline_config={}, uid=None,
                    owner=None, group=None, project=None, custom=None):
    data = locals()
    if custom:
        data.update(custom)
    payload = ujson.dumps(data)
    r = requests.post(_server_path + '/run_start_capped', data=payload)
    if r.status_code != 200:
        raise Exception("Server cannot complete the request", r)
    else:
        return r.json()


def _insert2cappedstop(run_start, time, uid=None, config={}, exit_status='success',
                    reason=None, custom=None):
    payload = ujson.dumps(locals())
    r = requests.post(_server_path + '/run_stop', data=payload)
    if r.status_code != 200:
        raise Exception("Server cannot complete the request", r)
    else:
        return r.json()


def monitor_run_stop():
    r = requests.get(_server_path + '/run_stop_capped')
    content = ujson.loads(r.text)
    yield utils.Document('RunStop', content)


def _normalize_human_friendly_time(val):
    """Given one of :
    - string (in one of the formats below)
    - datetime (eg. datetime.datetime.now()), with or without tzinfo)
    - timestamp (eg. time.time())
    return a timestamp (seconds since jan 1 1970 UTC).

    Non string/datetime.datetime values are returned unaltered.
    Leading/trailing whitespace is stripped.
    Supported formats:
    {}
    """
    # {} is placeholder for formats; filled in after def...

    tz = conf.connection_config['timezone']  # e.g., 'US/Eastern'
    zone = pytz.timezone(tz)  # tz as datetime.tzinfo object
    epoch = pytz.UTC.localize(datetime.datetime(1970, 1, 1))
    check = True

    if isinstance(val, six.string_types):
        # unix 'date' cmd format '%a %b %d %H:%M:%S %Z %Y' works but
        # doesn't get TZ?

        # Could cleanup input a bit? remove leading/trailing [ :,-]?
        # Yes, leading/trailing whitespace to match pandas behavior...
        # Actually, pandas doesn't ignore trailing space, it assumes
        # the *current* month/day if they're missing and there's
        # trailing space, or the month is a single, non zero-padded digit.?!
        val = val.strip()

        for fmt in _TS_FORMATS:
            try:
                ts = datetime.datetime.strptime(val, fmt)
                break
            except ValueError:
                pass

        try:
            if isinstance(ts, datetime.datetime):
                val = ts
                check = False
            else:
                raise TypeError('expected datetime.datetime,'
                                ' got {:r}'.format(ts))

        except NameError:
            raise ValueError('failed to parse time: ' + repr(val))

    if check and not isinstance(val, datetime.datetime):
        return val

    if val.tzinfo is None:
        # is_dst=None raises NonExistent and Ambiguous TimeErrors
        # when appropriate, same as pandas
        val = zone.localize(val, is_dst=None)

    return (val - epoch).total_seconds()


# human friendly timestamp formats we'll parse
_TS_FORMATS = [
    '%Y-%m-%d %H:%M:%S',
    '%Y-%m-%d %H:%M',  # these 2 are not as originally doc'd,
    '%Y-%m-%d %H',  # but match previous pandas behavior
    '%Y-%m-%d',
    '%Y-%m',
    '%Y']

# build a tab indented, '-' bulleted list of supported formats
# to append to the parsing function docstring below
_doc_ts_formats = '\n'.join('\t- {}'.format(_) for _ in _TS_FORMATS)

# fill in the placeholder we left in the previous docstring
_normalize_human_friendly_time.__doc__ = (
    _normalize_human_friendly_time.__doc__.format(_doc_ts_formats)
)



