"""campus.api.routes.timetable

API routes for the Timetable resource.
"""

import flask

import campus.model.timetable as tt
import campus.yapper
from campus import flask_campus
from campus.common import schema
from campus.common.errors import api_errors

from ..resources import timetable as timetable_resource

import campus.storage
import campus.model

bp = flask.Blueprint('timetable', __name__, url_prefix='/timetable')

def init_app(app: flask.Flask | flask.Blueprint) -> None:
    """Initialise timetable routes with the given Flask app/blueprint."""
    app.register_blueprint(bp)

@bp.get('/current')
@flask_campus.unpack_request
def get_current() -> flask_campus.JsonResponse:
    """Summary:
        Get the currently active timetable ID.

    Method:
        GET /timetable/current

    Query Parameters:
        None

    Responses:
        200 OK: dict
            {"value": timetable_id}
    """
    timetable_id = timetable_resource.get_current()
    return {'value': timetable_id}, 200

@bp.put('/current')
@flask_campus.unpack_request
def set_current(value: schema.CampusID) -> flask_campus.JsonResponse:
    """Summary:
        Set the currently active timetable.

    Method:
        PUT /timetable/current

    Body Parameters:
        value: CampusID
            The timetable ID to set as the current timetable.

    Responses:
        200 OK: dict
            {}
    """
    timetable_resource.set_current(value)
    return {}, 200

@bp.get('/next')
def get_next() -> flask_campus.JsonResponse:
    """Summary:
        Get the next scheduled timetable ID.

    Method:
        GET /timetable/next

    Query Parameters:
        None

    Responses:
        200 OK: dict
            {"value": timetable_id}
    """
    timetable_id = timetable_resource.get_next()
    return {'value': timetable_id}, 200

@bp.put('/next')
@flask_campus.unpack_request
def set_next(value: schema.CampusID) -> flask_campus.JsonResponse:
    """Summary:
        Set the next scheduled timetable.

    Method:
        PUT /timetable/next

    Body Parameters:
        value: CampusID
            The timetable ID to set as the next timetable.

    Responses:
        200 OK: dict
            {}
    """
    timetable_resource.set_next(value)
    return {}, 200

@bp.post('/')
@flask_campus.unpack_request
def new(
    metadata: dict,
    data: dict
) -> flask_campus.JsonResponse:
    """Summary:
        Create a new timetable.

    Method:
        POST /timetable/

    Body Parameters:
        metadata: dict
            Metadata for the timetable, e.g. start and end date.

        data: dict
            The actual timetable data, e.g. entries.

    Responses:
        200 OK: dict
           {"data": timetable resource}

        400 Bad Request: dict
            {"error": error message}
    """

    try:
        timetable = timetable_resource.new(**metadata, lessongroups=data['lessongroups'])
    except Exception as e:
        return {'error': e}, 400

    return {"data": timetable.to_resource()}, 200

@bp.get('/<timetable_id>/')
@flask_campus.unpack_request
def get_timetable(timetable_id: schema.CampusID) -> flask_campus.JsonResponse:
    """Summary:
        Returns timetable metadata and entries in a single JSON object.
    Method:
        GET /timetable/<timetable_id>/
    Path Parameters:
        timetable_id: CampusID
            The ID of the timetable to retrieve.
    Responses:
        200 OK: dict
            {"timetable": timetable resource}
    """
    timetable = timetable_resource[timetable_id].get()
    return {"timetable": timetable.to_resource()}, 200
    

@bp.get('/<timetable_id>/entries')
@flask_campus.unpack_request
def get_timetable_entries(timetable_id: schema.CampusID) -> flask_campus.JsonResponse:
    """Summary:
        List all timetable entries for a specific timetable and user.

    Method:
        GET /timetable/<timetable_id>/entries

    Path Parameters:
        timetable_id: CampusID
            The ID of the timetable to retrieve.

    Responses:
        200 OK: dict
            {"entries": [timetable entry resources]}
    """
    result = timetable_resource[timetable_id].entries.list()
    return {'entries': [entry.to_resource() for entry in result]}, 200
    

@bp.get('/<timetable_id>/metadata')
@flask_campus.unpack_request
def get_timetable_metadata(timetable_id: schema.CampusID):
    """Summary:
        Get metadata for a specific timetable.

    Method:
        GET /timetable/<timetable_id>/metadata

    Path Parameters:
        timetable_id: CampusID
            The ID of the timetable.

    Responses:
        200 OK: dict
            timetable metadata resource
    """
    timetable = timetable_resource[timetable_id].metadata.get()
    return timetable.to_resource(), 200

@bp.patch('/<timetable_id>/metadata')
@flask_campus.unpack_request
def set_metadata(timetable_id: schema.CampusID, start_date: schema.DateTime, end_date: schema.DateTime) -> flask_campus.JsonResponse:
    """Summary:
        Update metadata for a specific timetable.

    Method:
        PATCH /timetable/<timetable_id>/metadata

    Path Parameters:
        timetable_id: CampusID
            The ID of the timetable.

    Body Parameters:
        start_date: DateTime
            The new start date of the timetable.
        end_date: DateTime
            The new end date of the timetable.

    Responses:
        200 OK: dict
            {}
    """
    timetable_resource[timetable_id].metadata.update(
        start_date=start_date,
        end_date=end_date
    )
    return {}, 200
