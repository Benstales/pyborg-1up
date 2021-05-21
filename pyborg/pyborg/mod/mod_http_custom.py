"""
pyborg http server for multiplexing backend/brain access
"""

import inspect
import logging
from typing import Callable
from pathlib import Path
from typing import List, Dict

import bottle
import click
import attr
from bottle import request
from filelock import FileLock

from pyborg.util.pyborg_custom import PyborgBot
from pyborg.util.stats import send_stats

logger = logging.getLogger(__name__)
folder = click.get_app_dir("Pyborg")
SAVE_LOCK = FileLock(Path(folder, ".pyborg_is_saving.lock"))

try:
    import nltk
    logger.debug("Got nltk!")
except ImportError:
    nltk = None
    logger.debug("No nltk, won't be using advanced part of speech tagging.")


@attr.s
class BottledPyborg:
    brain_path = attr.ib()
    toml_path = attr.ib()
    pyb = attr.ib(init=False)

    def setup(self, app) -> None:
        self.pyb = PyborgBot(brain=Path(self.brain_path), toml_file=Path(self.toml_path))

    def close(self) -> None:
        logger.debug("bottled pyborg save via close() initiated.")
        with SAVE_LOCK:
            self.pyb.save_brain()

    def apply(self, callback, route) -> Callable:
        keyword = "pyborg"
        args = inspect.signature(route["callback"]).parameters
        if keyword not in args:
            return callback

        def wrapper(*args, **kwargs) -> Callable:
            kwargs[keyword] = self.pyb
            return callback(*args, **kwargs)

        return wrapper


@bottle.route("/")
def index(pyborg: PyborgBot) -> str:
    return f"""<html><h1>Welcome to PyBorg/http</h1>
    <h2>{pyborg.config["ver_string"]}</h2>
    <a href='/words.json'>Words info (json)</a>
    <h2>Is the db saving?</h2>
    <p>{SAVE_LOCK.is_locked}</p>
    </html>"""

# Basic API


@bottle.route("/learn", method="POST")
def learn(pyborg: PyborgBot) -> str:
    body = request.POST.getunicode("body")
    pyborg.learn(body)
    return "OK"


@bottle.route("/reply", method="POST")
def reply(pyborg: PyborgBot) -> str:
    body = request.POST.getunicode("body")
    owner = request.POST.get("owner")
    return pyborg.make_reply(body, owner=owner)


@bottle.route("/save", method="POST")
def save(pyborg: PyborgBot) -> str:
    with SAVE_LOCK:
        pyborg.save_brain()
        return f"Saved to {pyborg.brain}"


@bottle.route("/info")
def info(pyborg: PyborgBot) -> tuple:
    return pyborg.config["ver_string"], pyborg.brain


@bottle.route("/info.json")
def info2(pyborg: PyborgBot) -> Dict:
    return {"version_string": pyborg.config["ver_string"], "brain": pyborg.brain}


@bottle.route("/stats", method="POST")
def stats(pyborg: PyborgBot) -> str:
    "record stats to statsd"
    send_stats(pyborg)
    return "OK"


@bottle.route("/process", method="POST")
def process(pyborg: PyborgBot) -> str:
    body = request.POST.getunicode("body")
    owner = request.POST.get("owner")
    return pyborg.make_reply(body, owner=owner)


@bottle.route("/known")
def known(pyborg: PyborgBot) -> str:
    "return number of contexts"
    word = request.query.word
    try:
        return f"{word} is known ({len(pyborg.words[word])} contexts)"
    except KeyError:
        return "word not known"


@bottle.route("/words.json")
def words_json(pyborg: PyborgBot) -> Dict:
    return {"words": pyborg.settings["num_words"],
            "contexts": pyborg.settings["num_contexts"],
            "lines": len(pyborg.lines)}


@bottle.route("/commands.json")
def commands_json(pyborg: PyborgBot) -> Dict:
    return pyborg.command_dict.command_dict


@bottle.get("/meta/status.json")
def save_lock_status(pyborg: PyborgBot) -> Dict:
    return {"status": SAVE_LOCK.is_locked}


@bottle.post("/meta/logging-level")
def set_log_level() -> None:
    """levels = {"DEBUG": logging.DEBUG, "INFO": logging.INFO,
              "WARNING": logging.WARNING, "ERROR": logging.ERROR, "CRITICAL": logging.CRITICAL}
    """
    logger.setLevel(request.POST.get("level").upper())
