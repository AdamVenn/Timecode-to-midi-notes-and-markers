# Timecode-to-midi-notes-and-markers
Classes to make a midi file containing simple midi notes and markers from timecodes.

Requirements: Please also download my timecode library

I wanted to make a program for making midi files containing markers and midi notes to trigger wipes with the application, Streamers. (https://figure53.com/streamers/)

Example usage:

```
midi = MidiFile()

startTC = '00:01:00:00'
fps = 23.98
midi.startTC = Timecode(startTC, fps)
midi.fps = float(fps)

trackName = "My First Track"
midi.add_wipe_track(trackName)

midi.lstTrackWipes[0].add_wipe(Timecode('00:01:01:00', 23.98))

midi.add_marker('00:01:02:00, "My marker text")

savePath = '/Path/To/Save/file.mid'
midi.to_file(savePath)
```
