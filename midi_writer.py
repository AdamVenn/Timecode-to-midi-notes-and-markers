# Thanks to the BitArray library - I couldn't figure out how to do it with bitshifting!
# If you can teach me, please get in touch
# Also, thanks to Sounds in Sync.

import struct
import re
from collections import OrderedDict
from random import randint  # testing only
from tkinter import filedialog
from bitstring import BitArray
from timecode import Timecode


# --Calculation functions--
def vlv_to_int(vlv: bytes) -> int:
    """Calculate integer from variable-length time"""
    output = 0
    mask = 127  # 01111111
    for count, byte in enumerate(vlv[::-1]):
        b = mask & byte     # remove first bit
        c = b << (count*7)  # move to correct position in 'bit string'
        output |= c         # add to output

    return output


def int_to_vlv(number: int) -> bytes:
    """Calculate variable-length time from integer"""

    assert type(number) is int, "Input should be integer"
    assert number <= 4294967295, "Woah! Number too huge. Should be <= 4294967295 "

    # inputs below 127 don't change
    try:
        if number <= 127: return number.to_bytes(1, 'big')
    except OverflowError:
        print(number)

    # get input into bit array
    number = struct.pack('>I', number)  # must do big endian as midi values are read forward
    bits = BitArray(number)

    # remove 0s from beginning
    while bits[0] == 0:
        del(bits[0])

    length = len(bits)

    # insert 0 at the beginning of the final byte, signifying it is the final byte
    bits.insert(1, length-7)
    # insert 1s at beginning of each byte, shifting the rest left
    for pos in range(length)[length-14::-7]:
        bits.insert(1, pos)
        bits.invert(pos)

    # pad 0s to complete the first byte
    while len(bits) % 8 != 0:
        bits.insert(1,0)

    # make first bit 1 if not already
    if bits[0] is not True:
        bits.invert(0)

    return bits.bytes


def is_timecode(timecode:str)->bool:
    assert type(timecode) is str, "{} not string.".format(timecode)
    rex = re.compile('\d{2}:\d{2}:\d{2}(:|;)\d{2}$')
    return rex.match(timecode) is not None


def is_legal(text: str)->bool:
    assert type(text) is str
    return all(32 <= ord(c) < 127 for c in text)


class MidiFile():
    """ Class representing a midi file """
    def __init__(self):
        """Initialize everything that will be used to make the final midi file"""
        # Header Chunk
        self.headerMidiFile = OrderedDict()
        self.headerMidiFile['head'] = b'MThd'
        self.headerMidiFile['size'] = struct.pack('>I', 6)
        self.headerMidiFile['format'] = struct.pack('>H', 1)
        self.headerMidiFile['noTracks'] = struct.pack('>H', 1)   # must be changed later
        self.headerMidiFile['ticks-per-quarter-note'] = struct.pack('>H', 9600)

        self.tempo = (500000).to_bytes(3, 'big')
        self.fps = 23.976
        self.sampleRate = 48000.00
        self.startTC = Timecode('00:00:00:00', self.fps)

        self.ppq = 9600                                           # pulses/ticks per quarter-note/beat
        self.tpq = 500000                                         # time per quarter-note - 500,000 microseconds, ie. 0.5 seconds
        self.beatsPerSecond = 1000000//self.tpq                   # 2 beats per second, 120 bpm
        self.ticksPerSecond = self.ppq * self.beatsPerSecond      # 19,200 ticks per second
        self.ticksPerFrame = self.ticksPerSecond / self.fps       # 800 ticks per frame @ 24fps

        # Note: format 1 means the first track contains the global tempo data and no events
        #       this also means that the rest of the tracks should contain events and no timing data

        # global timing + markers track
        self.headerTrackOne = OrderedDict()
        self.headerTrackOne['track'] = b'MTrk'
        self.headerTrackOne['trkSize'] = struct.pack('>I', 1)   # will be changed later

        self.eventStartTC = OrderedDict()
        self.eventStartTC['offset'] = int_to_vlv(0)
        self.eventStartTC['code'] = b'\xff\x54'                 # midi meta event code
        self.eventStartTC['size'] = int_to_vlv(5)
        self.eventStartTC['startTC'] = b'\x00\x00\x00\x00\x00'  # change later

        self.eventTempo = OrderedDict()
        self.eventTempo['offset'] = int_to_vlv(0)
        self.eventTempo['code'] = b'\xff\x51'                   # midi meta event code
        self.eventTempo['size'] = int_to_vlv(3)
        self.eventTempo['tempo'] = self.tpq.to_bytes(3, 'big')

        self.lstMarkers = []

        self.trackOneEnd = b'\x00\xff\x2f\x00'

        self.lstTrackWipes = []

    def __repr__(self):
        return "A midi object with {} marker(s) and {} wipes track(s)".format(len(self.trackMarkers.lstMarkers), len(self.lstTrackWipes))

    def __str__(self):
        return "A midi object with {} marker(s) and {} wipes track(s)".format(len(self.trackMarkers.lstMarkers), len(self.lstTrackWipes))

    def ticks_to_samples(self, ticks: int) -> int:
        samplesPerTick = self.sampleRate / self.ticksPerSecond
        return round(ticks * samplesPerTick)

    def samples_to_ticks(self, samples: int) -> int:
        ticksPerSample = self.ticksPerSecond / self.sampleRate
        return round(samples * ticksPerSample)

    def timecode_to_ticks(self, timecode) -> int:
        assert timecode.fps == self.fps, "Frame rate of Timecode object does not match frame rate of midi object."
        # going to int and then pulling up is more accurate than going from float for some reason
        ticks = int(self.ticksPerFrame) * timecode.frames
        if self.fps in [23.976, '29.97 drop', '29.97 non-drop']:
            ticks = round(ticks * 1.001)
        return ticks

    def ticks_to_timecode(self, ticks: int):
        frames = round(ticks / self.ticksPerFrame)
        timecode = Timecode(frames, self.fps)
        return timecode

    def add_marker(self, time, text):
        """Add a marker to track one. Time is in absolute samples"""
        assert is_legal(text), "Illegal characters found in marker text."
        assert len(text) <= 32, "Marker name too long"
        if isinstance(time, Timecode):
            self.lstMarkers.append([time, text])
        elif isinstance(time, str) or isinstance(time, int):
            self.lstMarkers.append([Timecode(time, self.fps), text])
        else:
            raise ValueError("%s not valid for marker timecode." % time)

    def add_wipe_track(self, trackName):
        self.lstTrackWipes += [WipeTrack(self, trackName)]

    def calc_start_TC(self):
        """Set the start timecode bytes of the midi file based on the start TC and frame rate"""

        TC = str(self.startTC)
        fps = self.fps
        assert is_timecode(str(TC)), "Timecode not in correct format. ##:##:##:## or ##:##:##;## expected."

        h = int(TC[0:2])
        m = int(TC[3:5]).to_bytes(1, 'big')
        s = int(TC[6:8]).to_bytes(1, 'big')
        f = int(TC[9:11]).to_bytes(1, 'big')
        ff = (0).to_bytes(1, 'big')  # sub-frames

        # the hour byte is shared between hour and frame rate
        # adapting the frame rate:
        if   fps in (23.976, '23.976'):                   fps = '24'
        elif fps in (24, '24'):                           fps = '24'
        elif fps in (25, '25'):                           fps = '25'
        elif fps in (29.97, '29.97', '29.97 non-drop'):   fps = '30 non-drop'
        elif fps == '29.97 drop':                         fps = '30 drop'
        elif fps in (30, '30', '30 non-drop'):            fps = '30 non-drop'
        elif fps == '30 drop':                            fps = '30 drop'
        else:
            raise ValueError

        # get the correct bytes for each frame rate:
        dicFpsLookup = {
            '24':          BitArray('0b000'),
            '25':          BitArray('0b001'),
            '30 drop':     BitArray('0b010'),
            '30 non-drop': BitArray('0b011')
        }

        # creating the hybrid byte
        bitsHour = BitArray(h.to_bytes(1, 'big'))[-5:]
        bitsFps = dicFpsLookup[fps]
        bytHour = (bitsFps + bitsHour).bytes

        self.eventStartTC['startTC'] = bytHour + m + s + f + ff

    def marker_track_to_bytes(self) -> bytes:
        # Markers
        sortedMarkers = sorted(self.lstMarkers, key=lambda x: x[0])
        times = [marker[0] for marker in sortedMarkers]
        names = [marker[1].encode('utf-8') for marker in sortedMarkers]
        # offsetTimes = [time - self.startTC for time in times]
        offsetTimes = times
        assert all([time >= 0 for time in offsetTimes]), "Markers found before start timecode."
        offsetTimes.insert(0, self.startTC)
        tickTimes = [self.timecode_to_ticks(x) for x in offsetTimes]
        relativeTimes = [j - i for i, j in zip(tickTimes[:-1], tickTimes[1:])]
        variableLengthTimes = [int_to_vlv(x) for x in relativeTimes]
        bytMarkers = b''
        for i in range(len(variableLengthTimes)):
            bytMarkers += variableLengthTimes[i]
            bytMarkers += b'\xff\x06'
            bytMarkers += int_to_vlv(len(names[i]))
            bytMarkers += names[i]
        bytMarkers += self.trackOneEnd

        # other events
        bytStartTC = b''.join([v for k, v in self.eventStartTC.items()])
        bytTempo = b''.join([v for k, v in self.eventTempo.items()])

        # calculate header size
        self.headerTrackOne['trkSize'] = struct.pack('>I', len(bytStartTC + bytTempo + bytMarkers))

        # header
        bytHeaderTrackOne = b''.join([v for k, v in self.headerTrackOne.items()])

        # all together
        bytTrackOne = bytHeaderTrackOne + bytStartTC + bytTempo + bytMarkers

        return bytTrackOne

    def to_file(self, fp=None):
        """Output the Midi class instance to a .midi file"""

        if not fp:
            fp = filedialog.asksaveasfilename()

        self.calc_start_TC()

        bytTrackOne = self.marker_track_to_bytes()
        bytWipesTracks = b''.join([x.to_bytes() for x in self.lstTrackWipes])

        # Calculate all track sizes
        self.headerMidiFile['noTracks'] = struct.pack('>H', len(self.lstTrackWipes) + 1)  # it's here ready for when I make multitrack support
        bytHeaderMidi = b''.join([v for k, v in self.headerMidiFile.items()])

        # write file
        with open(fp, 'wb') as file:
            file.write(bytHeaderMidi)
            file.write(bytTrackOne)
            file.write(bytWipesTracks)


class WipeTrack():
    """ A Track containing midi events in a midi file """
    def __init__(self, parent, trackName):
        self.parent = parent
        self.header = OrderedDict()
        self.header['track'] = b'MTrk'
        self.header['trkSize'] = struct.pack('>I', 1)  # must be changed later

        self.eventTrackName = OrderedDict()
        self.eventTrackName['offset'] = b'\x00'
        self.eventTrackName['code'] = b'\xff\x03'  # midi meta event code
        self.eventTrackName['size'] = int_to_vlv(5)
        self.eventTrackName['text'] = b'Wipes'
        self.change_track_name(trackName)

        self.lstWipes = []

        self.trackEnd = b'\xff\x2f\x00'

    def __str__(self):
        return "Midi track '{}' containing {} wipes.".format(
            self.eventTrackName['text'].decode('utf-8'),
            len(self.lstWipes)
        )

    def add_wipe(self, time: int, note: int=64, dur: int=9600):
        """Add a midi event/wipe to the track"""

        note = Note(note)
        noteOn = b'\x90' + note.value.to_bytes(1, 'big') + b'\x50'
        noteOff = b'\x90' + note.value.to_bytes(1, 'big') + b'\x00'

        if isinstance(time, Timecode):
            self.lstWipes.append([time, noteOn, dur, noteOff])
        elif isinstance(time, str) or isinstance(time, int):
            self.lstWipes.append([Timecode(time, self.parent.fps), noteOn, dur, noteOff])
        else:
            raise ValueError("%s not valid for wipe timecode." % time)

    def change_track_name(self, newName):
        assert is_legal(newName), "Illegal characters found in name"
        assert len(newName) <= 32, "Track name too long"
        self.eventTrackName['text'] = newName.encode('utf-8')
        self.eventTrackName['size'] = int_to_vlv(len(self.eventTrackName['text']))

    def to_bytes(self):
        # Calculate relative times of all wipes
        sortedWipes = sorted(self.lstWipes, key=lambda x: x[0])
        times =      [wipe[0] for wipe in sortedWipes]
        lstNoteOn =  [wipe[1] for wipe in sortedWipes]
        lstDur =     [wipe[2] for wipe in sortedWipes]
        lstNoteOff = [wipe[3] for wipe in sortedWipes]
        assert all([time >= 0 for time in times]), "Wipes found before start timecode."
        times.insert(0, self.parent.startTC)
        tickTimes =     [self.parent.timecode_to_ticks(x) for x in times]
        relativeTimes = [tickTimes[1] - tickTimes[0]]
        for i in range(2, len(tickTimes)):
            relativeTimes.append(tickTimes[i] - tickTimes[i - 1] - lstDur[i - 1])

        # Get wipes into byte string
        bytWipes = b''
        for i in range(len(relativeTimes)):
            bytWipes += int_to_vlv(relativeTimes[i])
            bytWipes += lstNoteOn[i]
            bytWipes += int_to_vlv(lstDur[i])
            bytWipes += lstNoteOff[i]
        endPad = int_to_vlv(lstDur[-1])  # space after the last event
        bytWipes += endPad

        # Concatenate track name event and wipes into byte string
        bytEventTrackName = b''.join([v for k, v in self.eventTrackName.items()])
        bytTrackTwo = bytEventTrackName + bytWipes + self.trackEnd

        # Get track size to finalise header
        self.header['trkSize'] = struct.pack('>I', len(bytTrackTwo))
        bytHeader = b''.join([v for k, v in self.header.items()])

        return bytHeader + bytTrackTwo


class Note():
    """Represents the midi note value.
    Used to present the integer value used by the file as a note value for a human."""
    def __init__(self, val):
        self.tupNotes = (
            'C0',
            'C#0',
            'D0',
            'D#0',
            'E0',
            'F0',
            'F#0',
            'G0',
            'G#0',
            'A0',
            'A#0',
            'B0',
            'C1',
            'C#1',
            'D1',
            'D#1',
            'E1',
            'F1',
            'F#1',
            'G1',
            'G#1',
            'A1',
            'A#1',
            'B1',
            'C2',
            'C#2',
            'D2',
            'D#2',
            'E2',
            'F2',
            'F#2',
            'G2',
            'G#2',
            'A2',
            'A#2',
            'B2',
            'C3',
            'C#3',
            'D3',
            'D#3',
            'E3',
            'F3',
            'F#3',
            'G3',
            'G#3',
            'A3',
            'A#3',
            'B3',
            'C4',
            'C#4',
            'D4',
            'D#4',
            'E4',
            'F4',
            'F#4',
            'G4',
            'G#4',
            'A4',
            'A#4',
            'B4',
            'C5',
            'C#5',
            'D5',
            'D#5',
            'E5',
            'F5',
            'F#5',
            'G5',
            'G#5',
            'A5',
            'A#5',
            'B5',
            'C6',
            'C#6',
            'D6',
            'D#6',
            'E6',
            'F6',
            'F#6',
            'G6',
            'G#6',
            'A6',
            'A#6',
            'B6',
            'C7',
            'C#7',
            'D7',
            'D#7',
            'E7',
            'F7',
            'F#7',
            'G7',
            'G#7',
            'A7',
            'A#7',
            'B7',
            'C8',
            'C#8',
            'D8',
            'D#8'
        )
        if val in self.tupNotes:
            self.set_note(val)
        else:
            self.set_value(val)

        # Streamers color
        # TO DO: Add in streamers color list
        self.color = 'yellow'

    def __repr__(self):
        return self.note

    def __str__(self):
        return self.note

    def set_note(self, note):
        self.value = self.tupNotes.index(note) + 24
        self.note = note

    def set_value(self, val):
        if val not in range(24, 122):
            raise ValueError("Bad value given for midi note: {}. Please enter a number between 12 and 112 or a note on the keyboard.".format(val))
        else:
            self.note = self.tupNotes[val]
            self.value = val


# testing functions

def rand_word() -> str:
    length = 4
    word = ''
    for letter in range(length):
        word += chr(randint(97, 122))
    return word


def rand_TC() -> str:
    hr = randint(0, 23)
    return '{:02}:{:02}:{:02}:{:02}'.format(hr, randint(0,59), randint(0,59), randint(0,23))


if __name__ == "__main__":
    pass


