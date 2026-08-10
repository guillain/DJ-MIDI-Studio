# Serato MIDI Config Visualizer & Editor

A robust tool designed to simplify the management, visualization, and modification of complex Serato DJ Pro MIDI configuration files (XML).

## Features

- **XML Parsing & Modeling**: Automatically parses large Serato MIDI configuration files (XML), mapping them into a structured object-oriented model (Decks, Channels, Notes, Slots, etc.).
- **Visual Mapping Editor**: Provides a user-friendly interface to visualize and modify MIDI mappings, including object attributes (On/Off values, colors) and associated events (Click, Output).
- **Validation**: Ensures the integrity of the configuration after modifications to prevent mapping conflicts or invalid XML structures.
- **Export**: Generates a clean, valid XML file ready to be imported back into Serato DJ Pro.

## Technical References

To ensure compatibility and accuracy, this project integrates data from the following official documentation:

*   [Serato MIDI Mapping Guide](https://support.serato.com/hc/en-us/articles/209377487-MIDI-mapping-with-Serato-DJ-Pro)
*   [Pioneer DJ XDJ-XZ MIDI Message List](https://downloads.support.alphatheta.com/software_info/all-in-one-dj-systems/XDJ-XZ/XDJ-XZ_MIDI_Message_List_E3.pdf)
*   [Pioneer DJ DDJ-XP2 MIDI Message List](https://downloads.support.alphatheta.com/software_info/dj-controllers/DDJ-XP2/DDJ-XP2_MIDI_Message_List_E1.pdf)

## Project Goals

This application aims to remove the manual complexity of editing 16,000+ line XML files by providing a visual layer that abstracts the raw MIDI protocol, allowing DJs to focus on performance customization rather than syntax troubleshooting.

## Usage

1. **Import**: Load your existing `.xml` Serato MIDI configuration file.
2. **Visualize**: Navigate through the structured tree of controllers, decks, and mapped functions.
3. **Modify**: Update attributes, reassign notes, or change event triggers via the GUI.
4. **Validate**: Run the internal validator to check for mapping overlaps or syntax errors.
5. **Export**: Save your custom configuration to be used directly within Serato DJ Pro.