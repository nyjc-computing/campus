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
    timetable_id = timetable_resource.get_current()
    return {'data': timetable_id}, 200

@bp.put('/current')
@flask_campus.unpack_request
def set_current(UUID: schema.CampusID) -> flask_campus.JsonResponse:
    timetable_resource.set_current(UUID)
    return {}, 200

@bp.get('/next')
def get_next() -> flask_campus.JsonResponse:
    timetable_id = timetable_resource.get_next()
    return {'data': timetable_id}, 200

@bp.put('/next')
@flask_campus.unpack_request
def set_next(UUID: schema.CampusID) -> flask_campus.JsonResponse:
    timetable_resource.set_current(UUID)
    return {}, 200

@bp.post('/')
@flask_campus.unpack_request
def upload() -> flask_campus.JsonResponse:
    return {}, 501 # Not implemented yet

@bp.get('/<timetable_id>')
@flask_campus.unpack_request
def get_timetable(timetable_id: schema.CampusID, user_id: schema.UserID) -> flask_campus.JsonResponse:
    result = timetable_resource[timetable_id].list(user_id=user_id)
    return {'data': [entry.to_resource() for entry in result]}, 200
    

@bp.get('/<timetable_id>/metadata')
@flask_campus.unpack_request
def get_metadata(timetable_id: schema.CampusID):
    timetable = timetable_resource[timetable_id].get()
    return timetable.to_resource(), 200

@bp.patch('/<timetable_id>/metadata')
@flask_campus.unpack_request
def set_metadata(timetable_id: schema.CampusID, start_date: schema.DateTime, end_date: schema.DateTime) -> flask_campus.JsonResponse:
    timetable_resource[timetable_id].update(
        start_date=start_date,
        end_date=end_date
    )
    return {}, 200