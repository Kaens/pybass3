"""
    Pyside2 compatible Playlist object


"""
import logging
import pathlib

from PySide2 import QtCore

Qt = QtCore.Qt

from .pys2_song import Pys2Song
from .playlist import Playlist, PlaylistMode

log = logging.getLogger(__name__)

class Pys2Playlist(QtCore.QObject, Playlist):
    """
    Extension to the Playlist class which fires QT5/Pyside2 signals
    for when songs are added (group or individual), when the song changes, as well as reports when
    the state (play, pause, stop) occurs.

    """
    song_added = QtCore.Signal(str)  # Song ID, Qt DOES NOT like when I try to pass the Song object
    songs_added = QtCore.Signal(tuple) # the starting index and a list of Song ID's
    song_changed = QtCore.Signal(str)  # Song ID
    music_paused = QtCore.Signal(str)
    music_playing = QtCore.Signal(str)
    music_stopped = QtCore.Signal(str)

    queue_changed = QtCore.Signal()

    ticked = QtCore.Signal()

    def __init__(self, tick_precision = 500):
        QtCore.QObject.__init__(self)
        Playlist.__init__(self, Pys2Song)
        self.ticker = QtCore.QTimer()
        self.ticker.setInterval(tick_precision)

        self.ticker.timeout.connect(self.tick)

        log.debug("Initialized playlist: Precision is %s", tick_precision)


    def add_song(self, song_path: pathlib.Path, supress_emit = False) -> Pys2Song:
        log.debug("Pys2Playlist.add_song %s", song_path)
        song = super(Pys2Playlist, self).add_song(song_path)
        if supress_emit is False and song is not None:
            self.song_added.emit(song.id)

        return song

    def add_directory(self, dir_path: pathlib.Path, recurse=True, top = False, surpress_emit = True):
        """

        :param dir_path: The directory to scan for music
        :param recurse: Should sub directories be walked over
        :param Top: Is this the top level method in the recursion
        :return: A list of song_ids
        """
        log.debug("Playlist.add_directory called with %s", dir_path)
        dir_path = pathlib.Path(dir_path) # Make sure I am dealing with pathlib
        files = (file for file in dir_path.iterdir() if file.is_file() and file.suffix in self.VALID_TYPES)
        dirs = (fdir for fdir in dir_path.iterdir() if fdir.is_dir())

        index_position = -1 if top is False else len(self)+1
        song_ids = []

        for song_path in files:
            try:
                song = self.add_song(song_path, supress_emit= surpress_emit)
                if song is not None:
                    song_ids.append(song.id)
            except TypeError:
                pass


        if recurse is True:
            for fdir in dirs:
                _, sub_song_ids = self.add_directory(fdir, recurse)
                song_ids.extend(sub_song_ids)

        if top is True and surpress_emit is True:
            self.songs_added.emit((index_position, song_ids))

        return index_position, song_ids



    def play(self):
        log.debug("Pys2Playlist.play self.current is %s", self.current)
        new_song = False

        if self.current is None:
            new_song = True

        super(Pys2Playlist, self).play()
        if self.current is not None and self.current.is_playing:
            self.music_playing.emit(self.current.id)
            self.ticker.start()

        if new_song is True and self.current is not None:
            self.song_changed.emit(self.current.id)

    def play_song_by_index(self, song_index) -> Pys2Song:

        song = super(Pys2Playlist, self).play_song_by_index(song_index)

        self.song_changed.emit(song.id)
        self.music_playing.emit(song.id)

        return song

    def play_song_by_id(self, song_id) -> Pys2Song:
        song = super(Pys2Playlist, self).play_song_by_id(song_id)

        self.song_changed.emit(song.id)
        self.music_playing.emit(song.id)

        return song


    def play_first(self) -> Pys2Song:
        song = super(Pys2Playlist, self).play_first()
        if song is not None:
            self.song_changed.emit(song.id)
            self.music_playing.emit(song.id)
        return song

    def stop(self):
        log.debug("Pys2Playlist.stop called")

        super(Pys2Playlist, self).stop()
        if self.current is not None:
            self.music_stopped.emit(self.current.id)
            
        self.ticker.stop()

    def pause(self):
        log.debug("Pys2Playlist.pause called")
        super(Pys2Playlist, self).pause()
        if self.current is not None:
            self.music_paused.emit(self.current.id)

        self.ticker.stop()
        
    def previous(self):
        log.debug("Pys2Playlist.previous")
        result = super(Pys2Playlist, self).previous()
        log.debug("Pys2Playlist.previous changed to %r", result)
        if result is not None:
            self.song_changed.emit(result.id)
        
    def next(self):
        log.debug("Pys2Playlist.next")
        result = super(Pys2Playlist, self).next()
        log.debug("Next song is %r", result)
        if result is not None:
            self.song_changed.emit(result.id)

        return result


    def tick(self):

        if self.current is not None:
            remaining = self.current.remaining_bytes
            remaining_seconds = self.current.remaining_seconds
        else:
            log.debug("TICKER ACTIVE WITH NO SONG")
            self.ticker.stop()
            return

        if self.play_mode == PlaylistMode.loop_single and remaining <= 0:
            log.debug("TICK - Repeating %s", self.current.file_path)
            self.current.move2position_seconds(0)
            self.song_changed.emit(self.current.id)


        elif self.fade_in > 0 and remaining_seconds <= self.fade_in:
            if self.fadein_song is not None and remaining <= 0:
                log.debug("TICK - Fade in progress switching to current")
                self.current.stop()
                self.current.free_stream()
                self.current = self.fadein_song
                self.fadein_song = None
                self.queue_position += 1
                self.song_changed.emit(self.current.id)

            elif self.fadein_song is None and self.upcoming is not None:
                log.debug("TICK - fading in song")
                self.fadein_song = self.upcoming
                self.fadein_song.play()

        elif remaining <= 0 and self.current is not None:
            log.debug("TICK - current is finished, moving to next song")
            self.current.stop()
            self.current.free_stream()
            self.current = self.next()
            if self.current is not None:
                self.queue_position += 1
                self.current.play()
                self.song_changed.emit(self.current.id)

        self.ticked.emit()


    def set_sequential(self, restart_and_play = True):
        super(Pys2Playlist, self).set_sequential(restart_and_play=restart_and_play)
        self.queue_changed.emit()

    def set_randomize(self, restart_and_play=True):
        super(Pys2Playlist, self).set_randomize(restart_and_play=restart_and_play)
        self.queue_changed.emit()




