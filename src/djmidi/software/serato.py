"""Serato MIDI mapping software plugin."""

from djmidi.exporter import to_xml_string
from djmidi.parser import parse_string
from djmidi.software._registry import SoftwareDefinition, register

register(
    SoftwareDefinition(
        plugin_id="serato",
        name="Serato DJ",
        extensions=(".xml",),
        parser=parse_string,
        exporter=to_xml_string,
        display_order=10,
        capabilities=("mapping.parse", "mapping.export", "mapping.validate"),
        permissions=("mapping.read", "mapping.write"),
    )
)
