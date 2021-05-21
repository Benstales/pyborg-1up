import collections
import datetime
import json
import logging
import os
import random
import re
import math
import uuid
from typing import MutableMapping, List
from logging import Logger
from pathlib import Path
from random import randint
from typing import Any, Dict, Tuple, Union
from zlib import crc32

import attr
import click
import toml

from pyborg.pyborg import pyborg
from pyborg.commands_custom import PyborgCommandDict
from pyborg.commands_custom.internal import INTERNAL_COMMANDS
from pyborg.util.util_cli import mk_folder

from pyborg import __version__

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

MANDATORY_TOML_PARAMS = ["learning"]
# OPTIONAL_TOML_PARAMS map the key with its default value
OPTIONAL_TOML_PARAMS = {"ver_string": f"I am a version {__version__} Pyborg",
                        "saves_version": "1.4.0",
                        "owner": False,
                        "prefix": "!",
                        "censored": [],
                        "ignore_list": [],
                        'max_words': math.inf}

try:
    import nltk
    logger.debug("Got nltk!")
except ImportError:
    nltk = None
    logger.debug("No nltk, won't be using advanced part of speech tagging.")


def filter_message(message: str, bot) -> str:
    """
    Filter a message body so it is suitable for learning from and
    replying to. This involves removing confusing characters,
    padding ? and ! with ". " so they also terminate lines
    and converting to lower case.
    """
    # to lowercase
    message = message.lower()

    # remove garbage
    message = message.replace("\"", "")  # remove "s
    message = message.replace("\n", " ")  # remove newlines
    message = message.replace("\r", " ")  # remove carriage returns

    # remove matching brackets (unmatched ones are likely smileys :-) *cough*
    # should except out when not found.
    index = 0
    try:
        while 1:
            index = message.index("(", index)
            # Remove matching ) bracket
            i = message.index(")", index + 1)
            message = message[0:i] + message[i + 1:]
            # And remove the (
            message = message[0:index] + message[index + 1:]
    except ValueError as e:
        logger.debug("filter_message error: %s", e)

    message = message.replace(";", ",")
    message = message.replace("?", " ? ")
    message = message.replace("!", " ! ")
    message = message.replace(".", " . ")
    message = message.replace(",", " , ")
    message = message.replace("'", " ' ")
    message = message.replace(":", " : ")

    return message


@attr.s
class PyborgBot:
    """Pyborg Bot as a class"""

    brain: Union[Path, str] = attr.ib()
    toml_file: Union[Path, str] = attr.ib()
    command_dict: PyborgCommandDict = attr.ib(default=None)
    words: Dict[str, Dict[str, int]] = attr.ib(init=False)
    lines: Dict[int, Tuple[str, int]] = attr.ib(init=False)
    config: MutableMapping[str, Any] = attr.ib(init=False)
    settings: MutableMapping[str, Any] = attr.ib(init=False)
    ready: bool = attr.ib(default=False)
    has_nltk: bool = attr.ib(init=False)
    logger: Logger = attr.ib(default=logger)

    def __attrs_post_init__(self) -> None:
        self.brain = Path(self.brain)
        self.toml_file = Path(self.toml_file)

        # Load brain
        logger.info("Reading dictionary...")
        try:
            self.words, self.lines = pyborg.load_brain_json(self.brain.as_posix())
        except (EOFError, IOError) as e:
            # Create new database
            self.words = {}
            self.lines = {}
            logger.error(e)
            name = datetime.datetime.now().strftime("%m-%d-%y-auto-{}.pyborg.json").format(str(uuid.uuid4())[:4])
            self.brain = Path(click.get_app_dir("Pyborg"), "brains", name)
            logger.info("Error reading saves. New database created.")

        # Load TOML configuration file
        self.config = toml.load(self.toml_file)

        # Load commands
        self.command_dict = PyborgCommandDict.from_list_command(INTERNAL_COMMANDS, command_prefix=self.config["pyborg"]["prefix"])

        # Check if mandatory parameters are in indeed in the TOML configuration file
        miss_param = self.__check_config()
        if len(miss_param) != 0:
            raise BaseException("TOML configuration file miss mandatory parameter: " + miss_param)

        # Define the optional parameters by their default value if there are not present in the TOML configuration file
        for key, value in OPTIONAL_TOML_PARAMS.items():
            if key not in self.config["pyborg"]:
                self.config["pyborg"][key] = value
                logger.info(f"MISSING TOML PARAM {key} : default value {self.config['pyborg'][key]}")

        # Initialize the settings
        self.settings = {}
        mk_folder()

        logger.info("Updating dictionary information...")
        self.settings["num_words"] = len(self.words)
        num_contexts = 0
        # Get number of contexts
        for x in self.lines.keys():
            num_contexts += len(self.lines[x][0].split())
        self.settings["num_contexts"] = num_contexts

        # unlearn words in the unlearn.txt file.
        try:
            with open("unlearn.txt", 'r') as f:
                for line in f.readlines():
                    self.unlearn(line)
        except (EOFError, IOError) as e:
            logger.debug("No words to unlearn", exc_info=e)
        except FileNotFoundError as e:
            logger.debug("unlearn.txt file not found, no words to unlearn", exc_info=e)

        if nltk is None:
            self.has_nltk = False
        else:
            self.has_nltk = True

    def __repr__(self) -> str:
        return f"{self.config['pyborg']['ver_string']} with {len(self.words)} words and {len(self.lines)} lines. With a settings of: {self.config}"

    def __str__(self) -> str:
        return self.config["pyborg"]["ver_string"]

    def on_ready(self):
        """does nothing! implement or override. used internally for systemd notify."""
        pass

    def __check_config(self) -> List[str]:
        """Check the settings have all the mandatory parameters"""
        miss_params = []
        for key in MANDATORY_TOML_PARAMS:
            if key not in self.config["pyborg"]:
                miss_params.append(key)
        return miss_params

    def make_reply(self, body: str, owner: bool = False) -> str:
        #logger.debug("process_msg: %s", locals())
        # add trailing space so sentences are broken up correctly
        body = body + " "

        # Parse commands
        if body.startswith(self.config["pyborg"]["prefix"]):
            logger.debug("sending do_commands...")
            return self.do_commands(body, owner)

        # Filter out garbage and do some formatting
        body = filter_message(body, self)

        # Learn from input
        if self.config["pyborg"]["learning"]:
            self.learn(body)

        # Make a reply (all the time)
        return self.reply(body)

    def learn(self, body: str) -> None:
        self.learn_context(body)

    def save_brain(self) -> None:
        """
        Save brain as 1.4.0 JSON-Unsigned format
        """
        logger.info("Writing dictionary...")

        saves_version = u"1.4.0"
        logger.info("Saving pyborg brain to %s", self.brain.as_posix())
        cnt = collections.Counter()
        for key, value in self.words.items():
            cnt[type(key)] += 1
            # cnt[type(value)] += 1
            for i in value:
                cnt[type(i)] += 1
        #logger.debug("Types: %s", cnt)
        #logger.debug("Words: %s", self.words)
        #logger.debug("Lines: %s", self.lines)

        brain = {'version': saves_version, 'words': self.words, 'lines': self.lines}
        tmp_file = Path(click.get_app_dir("Pyborg"), "tmp", "current.pyborg.json")
        with open(tmp_file, 'w') as f:
            # this can fail half way...
            json.dump(brain, f)
        # if we didn't crash
        os.rename(tmp_file.as_posix(), self.brain.as_posix())
        logger.debug("Successful writing of brain & renaming. Quitting.")

    def do_commands(self, body: str, owner: bool = False) -> str:
        """
        Respond to user commands.
        """
        command_list = body.split()
        logger.debug("do_commands.command_list: %s", command_list)
        command_name = command_list[0].lower()[len(self.config["pyborg"]["prefix"]):]

        # Execute the command
        cmd = self.command_dict.get_command(command_name)
        if cmd is not None:
            res = cmd(self, command_list=command_list, owner=owner)
        else:
            res = "Command is not in the available command list."

        # Return the message (if any)
        if type(res) == str:
            return res
        else:
            return ""

    def replace(self, old: str, new: str) -> str:
        """
        Replace all occuraces of 'old' in the dictionary with
        'new'. Nice for fixing learnt typos.
        """
        try:
            pointers = self.words[old]
        except KeyError:
            return old + " not known."
        changed = 0

        for x in pointers:
            # pointers consist of (line, word) to self.lines
            l = self.words[x['hashval']]  # noqa: E741
            w = self.words[x['index']]
            line = self.lines[l][0].split()
            number = self.lines[l][1]
            if line[w] != old:
                # fucked dictionary
                print("Broken link: %s %s" % (x, self.lines[l][0]))
                continue

            line[w] = new
            self.lines[l][0] = " ".join(line)
            self.lines[l][1] += number
            changed += 1

        if new in self.words:
            self.settings["num_words"] -= 1
            self.words[new].extend(self.words[old])
        else:
            self.words[new] = self.words[old]
        del self.words[old]
        return "%d instances of %s replaced with %s" % (changed, old, new)

    def purge(self, max_contexts: int) -> int:
        "Remove rare words from the dictionary. Returns number of words removed."
        liste = []
        compteur = 0

        for w in self.words.keys():
            digit = 0
            char = 0
            for c in w:
                if c.isalpha():
                    char += 1
                if c.isdigit():
                    digit += 1

        # Compte les mots inferieurs a cette limite
            c = len(self.words[w])
            if c < 2 or (digit and char):
                liste.append(w)
                compteur += 1
                if compteur == max_contexts:
                    break

        if max_contexts < 1:
            logger.info("%s words to remove" % compteur, [])

        # supprime les mots
        for w in liste[0:]:
            self.unlearn(w)
        return len(liste[0:])

    def unlearn(self, context: str) -> None:
        """
        Unlearn all contexts containing 'context'. If 'context'
        is a single word then all contexts containing that word
        will be removed, just like the old !unlearn <word>
        """
        # Pad thing to look for
        # We pad so we don't match 'shit' when searching for 'hit', etc.
        context = " " + context + " "
        # Search through contexts
        # count deleted items
        dellist = []
        # words that will have broken context due to this
        wordlist = []
        for x in self.lines.copy().keys():
            # get context. pad
            c = " " + self.lines[x][0] + " "
            if c.find(context) != -1:
                # Split line up
                wlist = self.lines[x][0].split()
                # add touched words to list
                for w in wlist:
                    if w not in wordlist:
                        wordlist.append(w)
                dellist.append(x)
                del self.lines[x]
        words = self.words
        # update links
        for x in wordlist:
            word_contexts = words[x]
            # Check all the word's links (backwards so we can delete)
            for y in range(len(word_contexts) - 1, -1, -1):
                # Check for any of the deleted contexts
                hashval = word_contexts[y]['hashval']
                if hashval in dellist:
                    del word_contexts[y]
                    self.settings["num_contexts"] = self.settings["num_contexts"] - 1
            if len(words[x]) == 0:
                del words[x]
                self.settings["num_words"] = self.settings["num_words"] - 1
                logger.info(f" \"{x}\" vaped totally")

    def learn_context(self, body: str, num_context: int = 1) -> None:
        """
        Lines should be cleaned (filter_message()) before passing
        to this.
        """

        def learn_line(body: str, num_context: int) -> None:
            """
            Learn from a sentence.
            nb: there is a closure here...
            """
            logger.debug("entering learn_line")
            if nltk:
                words = nltk.word_tokenize(body)
            else:
                words = body.split()
            # Ignore sentences of < 1 words XXX was <3
            if len(words) < 1:
                return

            # voyelles = "aÃ Ã¢eÃ©Ã¨ÃªiÃ®Ã¯oÃ¶Ã´uÃ¼Ã»y"
            voyelles = "aeiouy"
            logger.debug("reply:learn_line:words: %s", words)
            for x in range(0, len(words)):

                nb_voy = 0
                digit = 0
                char = 0
                for c in words[x]:
                    if c in voyelles:
                        nb_voy += 1
                    if c.isalpha():
                        char += 1
                    if c.isdigit():
                        digit += 1

                for censored in self.config["pyborg"]["censored"]:
                    if re.search(censored, words[x]):
                        logger.debug("word: %s***%s is censored. escaping.", words[x][0], words[x][-1])
                        return
                if len(words[x]) > 13 \
                        or (((nb_voy * 100) / len(words[x]) <= 25) and len(words[x]) > 5) \
                        or (char and digit) \
                        or (words[x] in self.words) == 0 and not self.config["pyborg"]["learning"]:
                    # if one word as more than 13 characters, don't learn
                    # (in french, this represent 12% of the words)
                    # and d'ont learn words where there are less than 25% of voyels for words of more of 5 characters
                    # don't learn the sentence if one word is censored
                    # don't learn too if there are digits and char in the word
                    # same if learning is off
                    logger.debug(f"reply:learn_line: Bailing because reasons? Word: {words[x]}")
                    return
                elif "-" in words[x] or "_" in words[x]:
                    words[x] = "#nick"

            num_w = self.settings["num_words"]
            if num_w != 0:
                num_cpw = self.settings["num_contexts"] / float(num_w)  # contexts per word
            else:
                num_cpw = 0

            cleanbody = " ".join(words)

            # Hash collisions we don't care about. 2^32 is big :-)
            # Ok so this takes a bytes object... in python3 thats a pain
            cleanbody_b = bytes(cleanbody, "utf-8")
            # ok so crc32 got changed in 3...
            hashval = crc32(cleanbody_b) & 0xffffffff

            logger.debug(hashval)
            # Check context isn't already known
            if hashval not in self.lines:
                if not (num_cpw > 100 and not self.config["pyborg"]["learning"]):
                    self.lines[hashval] = [cleanbody, num_context]
                    # Add link for each word
                    for i, word in enumerate(words):
                    #for x in range(0, len(words)):
                        if word in self.words:
                            # Add entry. (line number, word number)
                            self.words[word].append({"hashval": hashval, "index": i})
                        else:
                            self.words[word] = [{"hashval": hashval, "index": i}]
                            self.settings["num_words"] += 1
                        self.settings["num_contexts"] += 1
            else:
                self.lines[hashval][1] += num_context

            # if max_words reached, don't learn more
            if self.settings["num_words"] >= self.config["pyborg"]["max_words"]:
                self.settings["learning"] = False

        # Split body text into sentences and parse them
        # one by one.
        body += " "
        logger.debug("reply:replying to %s", body)
        # map ( (lambda x : learn_line(self, x, num_context)), body.split(". "))
        for part in body.split('. '):
            learn_line(part, num_context)

    def reply(self, body) -> str:
        """
        Reply to a line of text.
        """
        # split sentences into list of words
        _words = body.split(" ")
        words = []
        for i in _words:
            words += i.split()

        if len(words) == 0:
            logger.debug("Did not find any words to reply to.")
            return ""

        # remove words on the ignore list
        words = [x for x in words if x not in self.config["pyborg"]["ignore_list"] and not x.isdigit()]
        logger.debug("reply: cleaned words: %s", words)
        # Find rarest word (excluding those unknown)
        index = []
        known = -1
        # The word has to have been seen in already 3 contexts differents for being choosen
        known_min = 3
        for w in words:
            # logger.debug("known_loop: locals: %s", locals())
            if w in self.words:
                k = len(self.words[w])
                #logger.debug("known_loop: k?? %s", k)
            else:
                continue
            if (known == -1 or k < known) and k > known_min:
                index = [w]
                known = k
                continue
            elif k == known:
                index.append(w)
                continue
        # Index now contains list of rarest known words in sentence
        # index = words

        # def find_known_words(words):
        #     d = dict()
        #     for w in words:
        #         if w in self.words:
        #             logger.debug(self.words[w])
        #             k = len(self.words[w])
        #             d[w] = k
        #     logger.debug("find_known_words: %s", d)
        #     idx = [x for x,y  in d.items() if y > 3]
        #     logger.debug("find_known_words: %s", idx)
        #     return idx

        # index = find_known_words(words)

        if len(index) == 0:
            logger.debug("No words with atleast 3 contexts were found.")
            logger.debug("reply:index: %s", index)
            return ""

        # Begin experimental NLP code
        def weight(pos: str) -> int:
            """Takes a POS tag and assigns a weight
            New: doubled the weights in 1.4"""
            lookup = {"NN": 8, "NNP": 10, "RB": 4, "NNS": 6, "NNPS": 10}
            try:
                ret = lookup[pos]
            except KeyError:
                ret = 2
            return ret

        def _mappable_nick_clean(pair: Tuple[str, str]) -> Tuple[str, int]:
            "mappable weight apply but with shortcut for #nick"
            word, pos = pair
            if word == "#nick":
                comp_weight = 1
            else:
                comp_weight = weight(pos)
            return (word, comp_weight)

        if nltk:
            # uses punkt
            tokenized = nltk.tokenize.casual.casual_tokenize(body)
            # uses averaged_perceptron_tagger
            tagged = nltk.pos_tag(tokenized)
            logger.info(tagged)
            weighted_choices = list(map(_mappable_nick_clean, tagged))
            population = [val for val, cnt in weighted_choices for i in range(cnt)]
            word = random.choice(population)
            # make sure the word is known
            counter = 0
            while word not in self.words and counter < 200:
                word = random.choice(population)
                counter += 1
            logger.debug("Ran choice %d times", counter)
        else:
            word = index[randint(0, len(index) - 1)]

        # Build sentence backwards from "chosen" word
        if self._is_censored(word):
            logger.debug("chosen word: %s***%s is censored. ignoring.", word[0], word[-1])
            return None
        sentence = [word]
        done = 0
        while done == 0:
            # create a dictionary wich will contain all the words we can found before the "chosen" word
            pre_words = {"": 0}
            # this is for prevent the case when we have an ignore_listed word
            word = str(sentence[0].split(" ")[0])
            for x in range(0, len(self.words[word]) - 1):
                #logger.debug(locals())
                logger.debug('trying to unpack: %s', self.words[word][x])
                l = self.words[word][x]['hashval']  # noqa: E741
                w = self.words[word][x]['index']
                context = self.lines[l][0]
                num_context = self.lines[l][1]
                cwords = context.split()
                # if the word is not the first of the context, look the previous one
                if cwords[w] != word:
                    print(context)
                if w:
                    # look if we can found a pair with the choosen word, and the previous one
                    if len(sentence) > 1 and len(cwords) > w + 1:
                        if sentence[1] != cwords[w + 1]:
                            continue

                    # if the word is in ignore_list, look the previous word
                    look_for = cwords[w - 1]
                    if look_for in self.config["pyborg"]["ignore_list"] and w > 1:
                        look_for = cwords[w - 2] + " " + look_for

                    # saves how many times we can found each word
                    if look_for not in pre_words:
                        pre_words[look_for] = num_context
                    else:
                        pre_words[look_for] += num_context

                else:
                    pre_words[""] += num_context

            # Sort the words
            liste = list(pre_words.items())  # this is a view in py3
            liste.sort(key=lambda x: x[1])
            numbers = [liste[0][1]]
            for x in range(1, len(liste)):
                numbers.append(liste[x][1] + numbers[x - 1])

            # take one them from the list ( randomly )
            mot = randint(0, numbers[len(numbers) - 1])
            for x in range(0, len(numbers)):
                if mot <= numbers[x]:
                    mot = liste[x][0]
                    break

            # if the word is already choosen, pick the next one
            while mot in sentence:
                x += 1
                if x >= len(liste) - 1:
                    mot = ''
                logger.info("the choosening: %s", liste[x])
                mot = liste[x][0]

            # logger.debug("mot1: %s", len(mot))
            mot = mot.split()
            mot.reverse()
            if mot == []:
                done = 1
            else:
                list(map((lambda x: sentence.insert(0, x)), mot))

        pre_words = sentence
        sentence = sentence[-2:]

        # Now build sentence forwards from "chosen" word

        # We've got
        # cwords:    ... cwords[w-1] cwords[w]   cwords[w+1] cwords[w+2]
        # sentence:  ... sentence[-2]    sentence[-1]    look_for    look_for ?

        # we are looking, for a cwords[w] known, and maybe a cwords[w-1] known, what will be the cwords[w+1] to choose.
        # cwords[w+2] is need when cwords[w+1] is in ignored list
        done = 0
        while done == 0:
            # create a dictionary wich will contain all the words we can found before the "chosen" word
            post_words = {"": 0}
            word = str(sentence[-1].split(" ")[-1])
            for x in range(0, len(self.words[word])):
                l = self.words[word][x]['hashval']  # noqa: E741
                w = self.words[word][x]['index']
                context = self.lines[l][0]
                num_context = self.lines[l][1]
                cwords = context.split()
                # look if we can found a pair with the choosen word, and the next one
                if len(sentence) > 1:
                    if sentence[len(sentence) - 2] != cwords[w - 1]:
                        continue

                if w < len(cwords) - 1:
                    # if the word is in ignore_list, look the next word
                    look_for = cwords[w + 1]
                    if (look_for in self.config["pyborg"]["ignore_list"] or look_for in self.config["pyborg"]["censored"]) and w < len(cwords) - 2:
                        look_for = look_for + " " + cwords[w + 2]

                    if look_for not in post_words:
                        post_words[look_for] = num_context
                    else:
                        post_words[look_for] += num_context
                else:
                    post_words[""] += num_context
            # Sort the words
            liste = list(post_words.items())
            liste.sort(key=lambda x: x[1])
            numbers = [liste[0][1]]

            for x in range(1, len(liste)):
                numbers.append(liste[x][1] + numbers[x - 1])

            # take one them from the list ( randomly )
            mot = randint(0, numbers[len(numbers) - 1])
            for x in range(0, len(numbers)):
                if mot <= numbers[x]:
                    mot = liste[x][0]
                    break

            x = -1
            while mot in sentence:
                x += 1
                if x >= len(liste) - 1:
                    mot = ''
                    break
                mot = liste[x][0]

            # logger.debug("mot2: %s", len(mot))
            mot = mot.split()
            if mot == []:
                done = 1
            else:
                list(map(lambda x: sentence.append(x), mot))
        sentence = pre_words[:-2] + sentence
        # this seems bogus? how does this work???

        # Replace aliases
        for x in range(0, len(sentence)):
            if sentence[x][0] == "~":
                sentence[x] = sentence[x][1:]

        # Insert space between each words
        list(map((lambda x: sentence.insert(1 + x * 2, " ")), range(0, len(sentence) - 1)))

        # correct the ' & , spaces problem
        # code is not very good and can be improve but does his job...
        for x in range(0, len(sentence)):
            if sentence[x] == "'":
                sentence[x - 1] = ""
                sentence[x + 1] = ""
            if sentence[x] == ",":
                sentence[x - 1] = ""
        # logger.debug("final locals: %s", locals())
        # yolo
        for w in sentence:
            if self._is_censored(w):
                logger.debug(f"word in sentence: {w[0]}***{w[-1]} is censored. escaping.")
                return None
        final = "".join(sentence)
        return final

    def _is_censored(self, word: str) -> bool:
        """DRY."""
        for censored in self.config["pyborg"]["censored"]:
            if re.search(censored, word):
                logger.debug(f"word is censored: {word}")
                return True
        return False
