"""campus.model.timetable

Timetable model definitions for Campus. 

The timetable schema describes a schema that stores the 
following information from a timetable:
- Timeslots
- Lessons 
- Students and teachers involved in said lessons
- Venues

!!    The schema is documented in DETAIL by the `timetable.dbml` file. 
!!    Commenting both files would mean duplicate documentation.
!!    Please visualise it [here](https://dbml-editor.alswl.com/)!!!!
!!    The tool is also able to export the schema as SQL to create the respective tables.
"""

from typing import ClassVar
from dataclasses import dataclass, field

from campus.common import schema
from campus.common.schema.openapi import String, Integer, Boolean, DateTime
from campus.common.utils import uid

from .base import Model
from . import constraints

# NOTE: Assumes reusing the same object is not an issue
unique_field = field(metadata={
    "constraints": [constraints.UNIQUE],
})


@dataclass(eq=False, kw_only=True)
class WeekDay(Model):
    """
    Describes a day in a repeating timetable.
    """
    id: schema.CampusID = unique_field
    label: String
    index: Integer
    

@dataclass(eq=False, kw_only=True)
class TimeSlot(Model):
    """
    Timeslot which repeats across all `WeekDay`s
    """
    id: schema.CampusID = field(default_factory=(
        lambda: uid.generate_category_uid("timetable", length=8)
    ))
    label: String
    start_time: DateTime = unique_field
    end_time: DateTime = unique_field
    index: Integer = unique_field


@dataclass(eq=False, kw_only=True)
class Venue(Model):
    """
    Describes a single venue
    """
    id: schema.CampusID = field(default_factory=(
        lambda: uid.generate_category_uid("timetable", length=8)
    ))
    label: String


@dataclass(eq=False, kw_only=True)
class VenueTimeSlot(Model):
    """
    Imagine each venue has its own timetable.
    This is one timeslot on such a timetable, representing an intersection of
      Venue and TimeSlot
    """
    id: schema.CampusID = field(default_factory=(
        lambda: uid.generate_category_uid("timetable", length=8)
    ))
    weekday_id: schema.CampusID # FK -> weekday_id
    timeslot_id: schema.CampusID
    venue_id: schema.CampusID
    __constraints__ = constraints.Unique("weekday_id", "timeslot_id", "venue_id")


@dataclass(eq=False, kw_only=True)
class LessonGroup(Model):
    """
    This represents a specific lesson taught to a class.
    Eg. Chem, taught to 2510. (eg. stored as '2510-CM')
    """
    id: schema.CampusID = field(default_factory=(
        lambda: uid.generate_category_uid("timetable", length=8)
    ))
    filename: String
    label: String


@dataclass(eq=False, kw_only=True)
class LessonGroupMember(Model):
    """
    Represents a single member of a LessonGroup.
    For example, 2510-Math will have:
    - Rosaline Tan
    - All the students
    Where each individual is one LessonGroupMember.
    2510-Chem will have its own set of entries, even if the participant is duplicated.
    """
    id: schema.CampusID = field(default_factory=(
        lambda: uid.generate_category_uid("timetable", length=8)
    ))
    filename: String
    lessongroup_id: String
    ade_participant: String
    __constraints__ = constraints.Unique("lessongroup_id", "ade_participant", "filename")


@dataclass(eq=False, kw_only=True)
class Timetable(Model):
    """
    A timetable represents a lesson for a LessonGroup
    at some VenueTimeSlot
    """
    id: schema.CampusID = field(default_factory=(
        lambda: uid.generate_category_uid("timetable", length=8)
    ))
    filename: String
    lessongroup_id: String
    venuetimeslot_id: String
    __constraints__ = constraints.Unique("lessongroup_id", "venuetimeslot_id", "filename")
