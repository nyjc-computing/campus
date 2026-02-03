"""campus.model.timetable

Timetable model definitions for Campus. 

The timetable schema describes a schema that stores the 
following information from a timetable:
- Timeslots
- Lessons 
- Students and teachers involved in said lessons
- Venues

For all models, id is a CampusID with no relation to raw XML ID.

An allocation refers to a new set of classes, people and class timings
  imported with a new timetable. 
It refers to one of these:
  https://github.com/nyjc-computing/nyxchange-timetable-v2/blob/data-schema/tt_file/tt_xml_docs.md
This year's timetable and last year's timetable are two seperate allocations.
The data for an allocation is stored in some .xml file, named `filename`

TODO: Update doc link after migration
"""

from dataclasses import dataclass, field

from campus.common import schema
from campus.common.utils import uid

from .base import Model
from . import constraints

# NOTE: Assumes reusing the same object is not an issue
unique_field = field(metadata={
    "constraints": [constraints.UNIQUE],
})

##     Sections that stay constant or only have additions.       ##
##      They will be relevant every for every allocation.        ##

@dataclass(eq=False, kw_only=True)
class WeekDay(Model):
    """
    Describes a day in a repeating timetable.
    Assumption: This will stay constant across all allocations.

    Fields:
      label (String): (cosmetic purposes: 'Mon A', 'Tue A', ... 'Mon B', 'Tue B', ..., 'Sat', 'Sun')
      index (Integer): index 0 is earliest (eg. Mon A), followed by Tues A, etc.
    """
    id: schema.CampusID = unique_field
    label: schema.String
    index: schema.Integer
    

@dataclass(eq=False, kw_only=True)
class TimeSlot(Model):
    """
    Timeslot which repeats across all `WeekDay`s
    Assumption: This will stay constant across all allocations.

    Fields:
      label (String): (primarily cosmetic: '0730', '0800', ...)
      start_time (DateTime): ISO8601
      end_time (DateTime): ISO8601
      index (Integer): index 0 is earliest slot (eg. 0730), followed by 0800 at idx 1, etc.
    """
    id: schema.CampusID = field(default_factory=(
        lambda: uid.generate_category_uid("timetable", length=8)
    ))
    label: schema.String
    start_time: schema.DateTime = unique_field  # ISO8601
    end_time: schema.DateTime = unique_field  # ISO8601
    index: schema.Integer = unique_field


@dataclass(eq=False, kw_only=True)
class Venue(Model):
    """
    Describes a single venue.
    We have a set of venues that remain across years, except additions.
    Cannot refer to a group (eg. "All science labs").

    Fields:
      label (String): (e.g. '03-39', 'i-Space 1', ..., follow XML when possible)
    """
    id: schema.CampusID = field(default_factory=(
        lambda: uid.generate_category_uid("timetable", length=8)
    ))
    label: schema.String


@dataclass(eq=False, kw_only=True)
class VenueTimeSlot(Model):
    """
    Imagine each venue has its own timetable.
    This is one timeslot on such a timetable, representing an intersection of
      Venue and TimeSlot
    We use it for clean and convenient "timetable coordinates", as 
      we usually reason about an intersection of venue and time anyway
    Must be automatically generated for each Venue for all WeekDay, TimeSlot.

    Fields:
      weekday_id (CampusID): FK referencing a WeekDay.id
      timeslot_id (CampusID): FK referencing a TimeSlot.id
      venue_id (CampusID): FK referencing a Venue.id
    """
    id: schema.CampusID = field(default_factory=(
        lambda: uid.generate_category_uid("timetable", length=8)
    ))
    weekday_id: schema.CampusID
    timeslot_id: schema.CampusID
    venue_id: schema.CampusID
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
    
    Fields:
      filename (String): Allocation xml filename which this entry is relevant to
      label (String): Label brought over from xml, like 2527-COM
    """
    id: schema.CampusID = field(default_factory=(
        lambda: uid.generate_category_uid("timetable", length=8)
    ))
    filename: schema.String
    label: schema.String


@dataclass(eq=False, kw_only=True)
class LessonGroupMember(Model):
    """
    Represents a single member of a LessonGroup.
    For example, 2510-Math will have:
    - Rosaline Tan
    - All the students
    Where each individual is one LessonGroupMember.
    2510-Chem will have its own set of entries, even if the participant is duplicated.

    Fields:
      filename (String): Allocation xml filename which this entry is relevant to
      lessongroup_id (CampusID): FK referencing a LessonGroup.id
      ade_participant (String): XML id (aka TTCode or teacher_id). We have a unique mapping of these IDs
        to nyjc email etc., for each allocation.
    """
    id: schema.CampusID = field(default_factory=(
        lambda: uid.generate_category_uid("timetable", length=8)
    ))
    filename: schema.String
    lessongroup_id: schema.CampusID
    ade_participant: schema.String
    __constraints__ = constraints.Unique("lessongroup_id", "ade_participant", "filename")


@dataclass(eq=False, kw_only=True)
class Timetable(Model):
    """
    A timetable represents a single lesson for a LessonGroup
        at some VenueTimeSlot. 
    
    Fields:
      filename (String): Allocation xml filename which this entry is relevant to
      lessongroup_id (CampusID): FK referencing a LessonGroup.id
      venuetimeslot_id (CampusID): FK referencing a VenueTimeSlot.id
    """
    id: schema.CampusID = field(default_factory=(
        lambda: uid.generate_category_uid("timetable", length=8)
    ))
    filename: schema.String
    lessongroup_id: schema.CampusID
    venuetimeslot_id: schema.CampusID
    __constraints__ = constraints.Unique("lessongroup_id", "venuetimeslot_id", "filename")
