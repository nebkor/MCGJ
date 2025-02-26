from flask import Blueprint, render_template, request, redirect, url_for
from flask import session as client_session
from flask_login import current_user, login_required
import datetime
from . import db
from .models import Session, Track, User
from . import services

# Given a session number, fetch all tracks, and pass an array to the template.


bp = Blueprint("mcgj", __name__, template_folder="templates")


@bp.route("/")
def index():
    if current_user.is_authenticated:
        # Show list of past sessions
        sessions_query = "SELECT * FROM sessions"
        rows = db.query(sql=sessions_query)
        sessions = [Session(row) for row in rows]
        return render_template("session_list.html", sessions=sessions)
    else:
        # Log in page
        return render_template("login.html")


@bp.route("/profile")
@login_required
def profile():
    user_tracks_query = "SELECT * FROM tracks WHERE user_id = ? AND cue_date IS NOT NULL ORDER BY cue_date DESC LIMIT 50"
    user_tracks = db.query(sql=user_tracks_query, args=[current_user.id])
    user_tracks = [Track(row) for row in user_tracks]

    for track in user_tracks:
        d = track.cue_date.date()
        track.cue_date = d

    return render_template("edit_profile.html", user=current_user, tracks=user_tracks)

@bp.route("/update_profile", methods=['POST'])
@login_required
def update_profile():
    user = current_user
    user.nickname = request.form["nickname"] if request.form["nickname"] != "" else None
    user.update()
    return redirect(url_for('mcgj.profile'))

@bp.route("/sessions/<session_id>")
def render_session(session_id):
    if current_user.is_authenticated:
        """
        Renders a list of tracks for a given session.

        First, we fetch the tracks for this session from the database. We them pass them to the Jinja template for this view in the following objects:
        - unplayed: A list of all unplayed tracks for this session.
        - played: A dictionary with a key-value pair for each round. The keys are the round numbers, and the values are lists of the tracks, ordered by their cue dates.
        """
        session = Session(with_id=session_id)

        rows_query = "SELECT * FROM tracks WHERE session_id = ?"
        rows = db.query(sql=rows_query, args=[session_id])

        tracks = [Track(row) for row in rows]

        for track in tracks:
            if track.user_id:
                user_query = "SELECT nickname, name FROM users WHERE id = ?"
                user_rows = db.query(sql=user_query, args=[track.user_id])
                # temporarily set person field to canonical user info
                for user_row in user_rows:
                    if not user_row['nickname']:
                        track.person = user_row['name']
                    else:
                        track.person = user_row['nickname']

        unplayed_tracks = [track for track in tracks if track.played != 1]

        played_tracks = {}
        for round_num in range(1, session.current_round + 1):
            round_tracks = [track for track in tracks if track.round_number == round_num]
            played_tracks[round_num] = sorted([track for track in round_tracks if track.played == 1], key=lambda track: track.cue_date)

        is_driving = False
        if 'driving' in client_session:
            is_driving = client_session['driving'].get(session_id)

        # folks who have already gone this round
        round_users = [track.user_id for track in played_tracks[session.current_round]]
        # unique list of folks who haven't gone yet this round
        next_up_ids = {track.user_id for track in unplayed_tracks if track.user_id not in round_users}

        # sorry
        next_up_query = f"SELECT nickname, name FROM users WHERE id IN({','.join(['?']*len(next_up_ids))})"
        next_up_rows = db.query(sql=next_up_query, args=list(next_up_ids))

        next_up = []
        for person in next_up_rows:
            if not person['nickname']:
                next_up.append(person['name'])
            else:
                next_up.append(person['nickname'])

        return render_template("session_detail.html", session=session, unplayed=unplayed_tracks, played=played_tracks, is_driving=is_driving, next_up=next_up)

    else:
        return redirect(url_for('auth.session_auth_recurse_redirect', session_id=session_id))

@bp.route("/sessions/latest")
def renderLatestSession():
    session_query = "SELECT * FROM sessions ORDER BY create_date DESC limit 1"
    session_rows = db.query(sql=session_query)
    for session in session_rows:
        session_id = session['id']
        break
    if current_user.is_authenticated:
        return redirect(url_for('mcgj.render_session', session_id=session_id))
    else:
        return redirect(url_for('auth.session_auth_recurse_redirect', session_id=session_id))

@bp.route("/sessions/<session_id>/drive")
@login_required
def driveSession(session_id):
    if 'driving' not in client_session:
        client_session['driving'] = {}

    client_session['driving'][session_id] = True
    client_session.modified = True

    return redirect(url_for('mcgj.render_session', session_id=session_id))

@bp.route("/sessions/<session_id>/undrive")
@login_required
def undriveSession(session_id):
    if 'driving' not in client_session:
        client_session['driving'] = {}

    client_session['driving'][session_id] = False
    client_session.modified = True

    return redirect(url_for('mcgj.render_session', session_id=session_id))

@bp.route("/sessions/<session_id>/edit")
@login_required
def edit_session(session_id):
    """
    Renders a list of tracks for a given session.

    First, we fetch the tracks for this session from the database. We them pass them to the Jinja template for this view in the following objects:
    - unplayed: A list of all unplayed tracks for this session.
    - played: A dictionary with a key-value pair for each round. The keys are the round numbers, and the values are lists of the tracks, ordered by their cue dates.
    """
    print("edit {}".format(session_id))
    session = Session(with_id=session_id)
    return render_template("edit_session.html", session=session)


@bp.route("/sessions/<session_id>/update", methods=['POST'])
@login_required
def update_session(session_id):
    """Submit an update to a track"""
    session = Session(with_id=session_id)
    session.name = request.form["name"] if request.form["name"] != "" else None
    session.spotify_url = request.form["spotify_url"] if request.form["spotify_url"] != "" else None
    session.current_round = request.form["current_round"] if request.form["current_round"] != "" else None
    session.update()
    return redirect(url_for('mcgj.render_session', session_id=session_id))


@bp.route("/sessions/<session_id>/next_round")
@login_required
def next_round(session_id):
    """Update current round for session"""
    session = Session(with_id=session_id)
    session.current_round += 1
    session.update()

    return redirect(url_for('mcgj.render_session', session_id=session.id))


# We could make this accept GET, POST (to update) and DELETE methods, and
# conditionally pick the code we run based on the method, like
# https://pythonise.com/series/learning-flask/flask-http-methods
@bp.route("/tracks/<track_id>/edit")
@login_required
def render_edit_track(track_id):
    """Edit a track"""
    track = Track(with_id=track_id)
    user = User(with_id=track.user_id)
    if not user.nickname:
        track.person = user.name
    else:
        track.person = user.nickname
    return render_template("edit_track.html", track=track)


@bp.route("/tracks/<track_id>/update", methods=['POST'])
@login_required
def update_track(track_id):
    """Submit an update to a track"""
    track = Track(with_id=track_id)
    track.title = request.form["title"] if request.form["title"] != "" else None
    track.artist = request.form["artist"] if request.form["artist"] != "" else None
    track.url = request.form["url"] if request.form["url"] != "" else None
    sc = services.SpotifyClient()
    bc = services.BandcampClient()
    if sc.isSpotifyTrack(track.url):
        print("Spotify track detected!")
        spotify_title, spotify_artist, spotify_art_url = sc.getTrackInfo(track.url)
        if not track.title:
            track.title = spotify_title
        if not track.artist:
            track.artist = spotify_artist
        track.art_url = spotify_art_url
    elif bc.isBandcampTrack(track.url):
        print("Bandcamp track detected!")
        bandcamp_title, bandcamp_artist, bandcamp_art_url = bc.getTrackInfo(track.url)
        if not track.title:
            track.title = bandcamp_title
        if not track.artist:
            track.artist = bandcamp_artist
        track.art_url = bandcamp_art_url
    else:
        track.art_url = sc.getNonSpotifyArtwork(track)

    is_driving = False
    if 'driving' in client_session and str(track.session_id) in client_session['driving']:
        is_driving = client_session['driving'][str(track.session_id)]
    if track.user_id == current_user.id or is_driving == True:
        track.update()
    return redirect(url_for('mcgj.render_session', session_id=track.session_id))


@bp.route("/tracks/<track_id>/cue")
@login_required
def cue_track(track_id):
    """Submit an update to a track"""
    track = Track(with_id=track_id)
    # TODO: When we restruture the UI, this is where round number will get assigned
    # If the URL is a Spotify URL, add it to this session's playlist, otherwise open it.
    session = Session(with_id=track.session_id)
    track.round_number = session.current_round
    track.played = 1
    track.cue_date = datetime.datetime.now()

    track.update()
    return redirect(url_for('mcgj.render_session', session_id=track.session_id))


@bp.route("/tracks/<track_id>/uncue")
@login_required
def uncue_track(track_id):
    """Submit an update to a track"""
    track = Track(with_id=track_id)
    # Makes a track Unplayed
    track.played = 0
    track.update()
    return redirect(url_for('mcgj.render_session', session_id=track.session_id))


# I felt like this should use the DELETE method but… it doesn't work in HTML forms?
@bp.route("/tracks/<track_id>/delete")
@login_required
def delete_track(track_id):
    """Submit an update to a track"""
    track = Track(with_id=track_id)
    is_driving = False
    if 'driving' in client_session and str(track.session_id) in client_session['driving']:
        is_driving = client_session['driving'][str(track.session_id)]
    if track.user_id == current_user.id or is_driving == True:
        track.delete()
    return redirect(url_for('mcgj.render_session', session_id=track.session_id))


# TODO: New tracks don't need a round number, they'll get one at the time they are added to the current round
@bp.route("/new_track")
@login_required
# If we are able to pass in params, we can pass them in here for session_id and round_number.
def render_new_track():
    """Create a new track"""
    session = Session(with_id=request.args["session_id"])
    if 'name' not in client_session:
        client_session['name'] = ''
    return render_template("new_track.html", session=session, name=client_session['name'])


# TODO: Could probably be "tracks/insert"
@bp.route("/insert_track", methods=['POST'])
@login_required
def insert_track():
    """Insert a new track row"""
    print(request.form)
    track = Track(request.form)
    track.user_id = current_user.id
    # track.session_id = request.form["session_id"]
    # track.title = request.form["title"]
    # track.url = request.form["url"]

    sc = services.SpotifyClient()
    bc = services.BandcampClient()
    if sc.isSpotifyTrack(track.url):
        print("Spotify track detected!")
        spotify_title, spotify_artist, spotify_art_url = sc.getTrackInfo(track.url)
        if not track.title:
            track.title = spotify_title
        if not track.artist:
            track.artist = spotify_artist
        track.art_url = spotify_art_url
    elif bc.isBandcampTrack(track.url):
        print("Bandcamp track detected!")
        bandcamp_title, bandcamp_artist, bandcamp_art_url = bc.getTrackInfo(track.url)
        if not track.title:
            track.title = bandcamp_title
        if not track.artist:
            track.artist = bandcamp_artist
        track.art_url = bandcamp_art_url
    else:
        track.art_url = sc.getNonSpotifyArtwork(track)

    track.insert()
    print("ID of new track: {}".format(track.id))
    print(track.__dict__)
    return redirect(url_for('mcgj.render_session', session_id=track.session_id))


@bp.route("/insert_session")
@login_required
def insert_session():
    """Create a new session"""
    sess = Session()
    sess.name = "Recurse MCG {}".format(datetime.date.today().isoformat())
    sess.date = datetime.date.today()
    sess.current_round = 1
    sess.insert()
    return redirect(url_for('mcgj.render_session', session_id=sess.id))
