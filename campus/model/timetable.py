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
This year's timetable and last year's timetable are two separate allocations.
The data for an allocation is stored in some .xml file, named `filename`

Internal models not returned through APIs: 
- WeekDay, TimeSlot, VenueTimeSlot 
- use Integer IDs for their own id, and are referenced as such

Models that can be returned through APIs:
- LessonGroup, TimetableEntry, Timetable 
- use CampusID (UUID) for their own id, and are referenced as such

An ade_participant is an integer XML id. One ID corresponds to one teacher,
or one class-subject combi intersection (eg. 2510-COM/EC/P). Each Timetable, the mapping
changes. 

TODO: Update doc link after migration
"""

from dataclasses import dataclass, field
from typing import Any, Self

from campus.common import schema
from campus.common.utils import uid

from .base import Model
from . import constraints

# NOTE: Assumes reusing the same object is not an issue
unique_field = field(metadata={
    "constraints": [constraints.UNIQUE],
})

##      Sections that are only relevant to a specific allocation.       ##
##      New entries are created for each allocation.       ##
##      Which allocation the entry is relevant to is in timetable_id.       ##

@dataclass(eq=False, kw_only=True)
class LessonGroup(Model):
    """
    This represents a specific lesson (e.g. "pe mass (A)")
    - may involve multiple ADE participants
    - can occur multiple times in a week
    
    Fields:
      timetable_id (CampusID): FK referencing the timetable this lessongroup is relevant to
      label (String): Label brought over from xml, like 2527-COM
      members (list[String]): API-only list of lesson group members
      entries (list[TimetableEntry]): API-only list of entries for this group
    """
    id: schema.CampusID = field(default_factory=(
        lambda: uid.generate_category_uid("lesson-group", length=8)
    ))
    timetable_id: schema.CampusID 
    label: schema.String
    members: list[schema.String] = field(
        default_factory=list,
        metadata={"storage": False}
    )
    entries: list["TimetableEntry"] = field(
        default_factory=list,
        metadata={"storage": False}
    )
    __constraints__ = constraints.Unique("timetable_id", "label")

    def to_resource(self) -> dict[str, Any]:
        """Convert the LessonGroup to an API resource response."""
        return {
            "id": self.id,
            "created_at": self.created_at,
            "timetable_id": self.timetable_id,
            "label": self.label,
            "members": list(self.members),
            "entries": [entry.to_resource() for entry in self.entries],
        }


@dataclass(eq=False, kw_only=True)
class LessonGroupMember(Model):
    """
    Represents a single member of a LessonGroup.
    For example, 2510-Math will have:
    - Rosaline Tan
    - All the students
    Where each individual is one LessonGroupMember.
    2510-Chem will have its own set of member entries, even if the participant is duplicated.

    Fields:
      timetable_id (CampusID): FK referencing the timetable this lessongroup is relevant to
      lessongroup_id (CampusID): FK referencing a LessonGroup.id
      ade_participant (String): XML id (aka TTCode or teacher_id). We have a unique mapping of these IDs
        to nyjc email etc., for each allocation.
        A TTcode is an ID which corresponds to a class-subject combi intersection (eg. 2510-COM/EC/P)
    """
    id: schema.CampusID = field(default_factory=(
        lambda: uid.generate_category_uid("lesson-groupmember", length=8)
    ))
    timetable_id: schema.CampusID 
    lessongroup_id: schema.CampusID
    ade_participant: schema.String 
    __constraints__ = constraints.Unique("lessongroup_id", "ade_participant", "timetable_id")


@dataclass(eq=False, kw_only=True)
class TimetableEntry(Model):
    """
    A timetable entry represents a single lesson for a LessonGroup
        at some VenueTimeSlot. 
    
    For lessons that span multiple slots, there is an entry for each slot.
    For lessons that have multiple venues, there is an entry for each venue.
    If an event has no listed venue, the <Null> venue is used.
    
    Fields:
      timetable_id (CampusID): FK referencing the timetable this lessongroup is relevant to
      lessongroup_id (CampusID): FK referencing a LessonGroup.id
      venuetimeslot_id (Integer): FK referencing a VenueTimeSlot.id
    """
    id: schema.CampusID = field(default_factory=(
        lambda: uid.generate_category_uid("timetable-entry", length=16)
    ))
    timetable_id: schema.CampusID 
    lessongroup_id: schema.CampusID
    venue: schema.String  # e.g. "5-64"
    weekday: schema.String  # e.g. "Mon A"
    timeslot: schema.String  # e.g. "0800"
    __constraints__ = constraints.Unique("lessongroup_id", "venuetimeslot_id", "timetable_id")


##        Represents an allocation itself         ##
@dataclass(eq=False, kw_only=True)
class TimetableMetadata(Model):
    """
    The timetable represents an allocation.
    It refers to a new set of classes, people and class timings
        imported with each new timetable XML. 
    
    Fields:
      filename (String): The XML filename it was imported from
      start_date (DateTime): 00:00 on the first day the timetable comes into effect
      end_date (DateTime): 00:00 on the last day the timetable is effective
    """
    id: schema.CampusID = field(default_factory=(
        lambda: uid.generate_category_uid("timetable", length=8)
    ))
    filename: schema.String
    start_date: schema.DateTime 
    end_date: schema.DateTime 
    __constraints__ = constraints.Unique("filename")


@dataclass(eq=False, kw_only=True)
class Timetable(TimetableMetadata):
    """
    API representation of a timetable allocation.

    This model is meant for API representation, not for storage.
    It combines timetable metadata with:
    - a flat list of all timetable entries
    - a nested list of lesson groups, each with members and entries
    """
    entries: list[TimetableEntry] = field(default_factory=list)
    lessongroups: list[LessonGroup] = field(default_factory=list)

    # prevent accidental use of from_storage and to_storage
    @classmethod
    def from_storage(cls: type[Self], record: dict[str, Any]) -> Self:
        raise NotImplementedError(
            "Timetable.from_storage() is not supported. "
            "Use TimetableMetadata and TimetableEntry models instead."
        )

    def to_storage(self) -> dict[str, Any]:
        raise NotImplementedError(
            "Timetable.to_storage() is not supported. "
            "Use TimetableMetadata and TimetableEntry models instead."
        )

    def to_resource(self) -> dict[str, Any]:
        """Convert the Timetable to an API resource response."""
        return {
            "id": self.id,
            "created_at": self.created_at,
            "filename": self.filename,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "entries": [entry.to_resource() for entry in self.entries],
            "lessongroups": [
                lessongroup.to_resource()
                for lessongroup in self.lessongroups
            ],
        }
