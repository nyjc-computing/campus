"""campus.model.timetable

Timetable model definitions for Campus. 

The timetable schema describes a schema that stores the 
following information from a timetable:
- Timeslots
- Lessons 
- Students and teachers involved in said lessons
- Venues
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

# For all, id is a CampusID with no relation to raw XML ID.

# An allocation refers to a new set of classes, people and class timings
#   imported with a new timetable. 
# It refers to one of these:
#   https://github.com/nyjc-computing/nyxchange-timetable-v2/blob/data-schema/tt_file/tt_xml_docs.md
# This year's timetable and last year's timetable are two seperate allocations.
# The data for an allocation is stored in some .xml file, named `filename`


##     Sections that stay constant or only have additions.       ##
##      They will be relevant every for every allocation.        ##


@dataclass(eq=False, kw_only=True)
class WeekDay(Model):
    """
    Describes a day in a repeating timetable.
    Assumption: This will stay constant across all allocations.
    """
    id: schema.CampusID = unique_field
    label: String # (cosmetic purposes: 'Mon A', 'Tue A', ... 'Mon B', 'Tue B', ..., 'Sat', 'Sun')
    index: Integer # index 0 is earliest (eg. Mon A), followed by Tues A, etc.
    

@dataclass(eq=False, kw_only=True)
class TimeSlot(Model):
    """
    Timeslot which repeats across all `WeekDay`s
    Assumption: This will stay constant across all allocations.
    """
    id: schema.CampusID = field(default_factory=(
        lambda: uid.generate_category_uid("timetable", length=8)
    ))
    label: String # (primarily cosmetic: '0730', '0800', ...)
    start_time: DateTime = unique_field # ISO8601
    end_time: DateTime = unique_field # ISO8601
    index: Integer = unique_field # index 0 is slot (eg. 0730), followed by 0800, etc.


@dataclass(eq=False, kw_only=True)
class Venue(Model):
    """
    Describes a single venue.
    We have a set of venues that remain across years, except additions.
    Cannot refer to a group (eg. "All science labs").
    """
    id: schema.CampusID = field(default_factory=(
        lambda: uid.generate_category_uid("timetable", length=8)
    ))
    label: String # (e.g. '03-39', 'i-Space 1', ..., follow XML when possible)


@dataclass(eq=False, kw_only=True)
class VenueTimeSlot(Model):
    """
    Imagine each venue has its own timetable.
    This is one timeslot on such a timetable, representing an intersection of
      Venue and TimeSlot
    We use it for clean and convenient "timetable coordinates", as 
      we usually reason about an intersection of venue and time anyway
    Must be automatically generated for each Venue for all WeekDay, TimeSlot.
    """
    id: schema.CampusID = field(default_factory=(
        lambda: uid.generate_category_uid("timetable", length=8)
    ))
    weekday_id: schema.CampusID # FK -> WeekDay.id
    timeslot_id: schema.CampusID # FK -> TimeSlot.id
    venue_id: schema.CampusID # FK -> Venue.id
    __constraints__ = constraints.Unique("weekday_id", "timeslot_id", "venue_id")

##      Sections that are only relevant to a specific allocation.       ##
##      New entries are created for each allocation.       ##
##      Which allocation the entry is relevant to is .       ##

@dataclass(eq=False, kw_only=True)
class LessonGroup(Model):
    """
    This represents a specific subject taught to a class.
    Eg. Chem, taught to 2510. (eg. stored as '2510-CM')
    These are labelled as an inconsistently formatted string, imported
      directly from the XML. It seems we cannot seperate class and subject.
    """
    id: schema.CampusID = field(default_factory=(
        lambda: uid.generate_category_uid("timetable", length=8)
    ))
    filename: String # Allocation xml filename which this group is relevant to
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
    lessongroup_id: String # Ref -> LessonGroup.id
    # ade -> XML id (aka TTCode or teacher_id). We have a unique mapping of these IDs
    # to nyjc email etc., for each allocation.
    ade_participant: String
    __constraints__ = constraints.Unique("lessongroup_id", "ade_participant", "filename")


@dataclass(eq=False, kw_only=True)
class Timetable(Model):
    """
    A timetable represents a single lesson for a LessonGroup
        at some VenueTimeSlot. 
    """
    id: schema.CampusID = field(default_factory=(
        lambda: uid.generate_category_uid("timetable", length=8)
    ))
    filename: String
    lessongroup_id: String # Ref -> LessonGroup.id
    venuetimeslot_id: String # Ref -> VenueTimeSlot.id
    __constraints__ = constraints.Unique("lessongroup_id", "venuetimeslot_id", "filename")
