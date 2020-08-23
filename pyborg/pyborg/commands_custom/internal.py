"""
Module containing the internal commands
"""
from typing import List

from pyborg.pyborg_custom import PyborgBot
from pyborg.commands_custom import PyborgCommand

import time
import sys


def version(pyborg: PyborgBot, **kwargs) -> str:
    """Retrieve the pyborg version in string format."""
    return pyborg.config["pyborg"]["ver_string"]


def words(pyborg: PyborgBot, **kwargs) -> str:
    num_w = pyborg.settings["num_words"]
    num_c = pyborg.settings["num_contexts"]
    num_l = len(pyborg.lines)
    if num_w != 0:
        num_cpw = num_c / float(num_w)  # contexts per word
    else:
        num_cpw = 0.0
    return "I know %d words (%d contexts, %.2f per word), %d lines." % (num_w, num_c, num_cpw, num_l)


def save(pyborg: PyborgBot, **kwargs) -> str:
    pyborg.save_brain()
    return "Dictionary saved"


def help_pyborg(pyborg: PyborgBot, command_list: List[str] = None, **kwargs) -> str:
    if len(command_list) > 1:
        # Help for a specific command
        cmd = command_list[1].lower()
        if cmd in pyborg.command_dict:
            return pyborg.command_dict.get_command(cmd).display_help()
    else:
        return str(pyborg.command_dict)


def limit(pyborg: PyborgBot, command_list: List[str] = None, **kwargs) -> str:
    msg = "The max limit is "
    if len(command_list) == 1:
        msg += str(pyborg.config["max_words"])
    else:
        limit_var = int(command_list[1].lower())
        pyborg.config["max_words"] = limit_var
        msg += "now " + command_list[1]
    return msg


def rebuild_dict(pyborg: PyborgBot, **kwargs) -> str:
    if pyborg.config["pyborg"]["learning"]:
        t = time.time()

        old_lines = pyborg.lines
        old_num_words = pyborg.settings["num_words"]
        old_num_contexts = pyborg.settings["num_contexts"]

        pyborg.words = {}
        pyborg.lines = {}
        pyborg.settings["num_words"] = 0
        pyborg.settings["num_contexts"] = 0

        for k in old_lines.keys():
            pyborg.learn_context(old_lines[k][0], old_lines[k][1])

        return "Rebuilt dictionary in %0.2fs. Words %d (%+d), contexts %d (%+d)" % (
            time.time() - t, old_num_words, pyborg.settings["num_words"] - old_num_words, old_num_contexts,
            pyborg.settings["num_contexts"] - old_num_contexts)


def purge(pyborg: PyborgBot, command_list: List[str] = None, **kwargs) -> str:
    t = time.time()
    if len(command_list) == 2:
        # limite d occurences a effacer
        c_max = int(command_list[1])
    else:
        c_max = 0
    number_removed = pyborg.purge(c_max)
    return "Purge dictionary in %0.2fs. %d words removed" % (time.time() - t, number_removed)


def replace(pyborg: PyborgBot, command_list: List[str] = None, **kwargs) -> str:
    if len(command_list) < 3:
        return ""
    old = command_list[1].lower()
    new = command_list[2].lower()
    return pyborg.replace(old, new)


def unlearn(pyborg: PyborgBot, command_list: List[str] = None, **kwargs) -> str:
    # build context we are looking for
    context = " ".join(command_list[1:])
    context = context.lower()
    if context == "":
        return ""
    print("Looking for: " + context)
    # Unlearn contexts containing 'context'
    t = time.time()
    pyborg.unlearn(context)
    # we don't actually check if anything was
    # done..
    return "Unlearn done in %0.2fs" % (time.time() - t)


def learning(pyborg: PyborgBot, command_list: List[str] = None, **kwargs) -> str:
    msg = "Learning mode "
    if len(command_list) == 1:
        if not pyborg.config["pyborg"]["learning"]:
            msg += "off"
        else:
            msg += "on"
    else:
        toggle = command_list[1].lower()
        if toggle == "on":
            msg += "on"
            pyborg.config["pyborg"]["learning"] = True
        else:
            msg += "off"
            pyborg.config["pyborg"]["learning"] = False
    return msg


def censor(pyborg: PyborgBot, command_list: List[str] = None, **kwargs) -> str:
    msg = "s"
    # no arguments. list censored words
    if len(command_list) == 1:
        if len(pyborg.config["censored"]) == 0:
            msg = "No words censored"
        else:
            msg = "I will not use the word(s) %s" % ", ".join(pyborg.config["censored"])
    # add every word listed to censored list
    else:
        for x in range(1, len(command_list)):
            if command_list[x] in pyborg.config["censored"]:
                msg += "%s is already censored" % command_list[x]
            else:
                pyborg.config["censored"].append(command_list[x].lower())
                pyborg.unlearn(command_list[x])
                msg += "done"
            msg += "\n"
    return msg


def uncensor(pyborg: PyborgBot, command_list: List[str] = None, **kwargs) -> str:
    # Remove everyone listed from the ignore list
    # eg !unignore tom dick harry
    msg = ""
    for x in range(1, len(command_list)):
        try:
            pyborg.config["censored"].remove(command_list[x].lower())
            msg = "done"
        except ValueError as e:
            pyborg.logger.exception(e)
    return msg


def quit(pyborg: PyborgBot, **kwargs):
    # Close the dictionary
    pyborg.save_brain()
    sys.exit()


INTERNAL_COMMANDS = [PyborgCommand(name="version",
                                   command_callable=version,
                                   help="Usage: !version\nDisplay what version of Pyborg we are running"),
                     PyborgCommand(name="words",
                                   command_callable=words,
                                   help="Usage: !words\nDisplay how many words are known"),
                     PyborgCommand(name="save",
                                   command_callable=save,
                                   help="Save current brain to JSON file.",
                                   owner_permission=True),
                     PyborgCommand(name="help",
                                   command_callable=help_pyborg,
                                   help="Usage: !help [command]\nPrints information about using a command, "
                                        "or a list of commands if no command is given"),
                     PyborgCommand(name="limit",
                                   command_callable=limit,
                                   help="Usage: !limit [number]\nSet the number of words that pyBorg can learn.",
                                   owner_permission=True),
                     PyborgCommand(name="rebuilddict",
                                   command_callable=rebuild_dict,
                                   help="Owner command. Usage: !rebuilddict\nRebuilds dictionary links from the lines "
                                        "of known text. Takes a while. You probably don't need to do it unless your "
                                        "dictionary is very screwed",
                                   owner_permission=True),
                     PyborgCommand(name="purge",
                                   command_callable=purge,
                                   help="Usage: !purge [number]\nRemove all occurances of the words that appears in "
                                        "less than <number> contexts",
                                   owner_permission=True),
                     PyborgCommand(name="replace",
                                   command_callable=replace,
                                   help="Usage: !replace <old> <new>\nReplace all occurances of word <old> in the "
                                        "dictionary with <new>",
                                   owner_permission=True),
                     PyborgCommand(name="unlearn",
                                   command_callable=unlearn,
                                   help="Usage: !unlearn <expression>\nRemove all occurances of a word or expression "
                                        "from the dictionary. For example '!unlearn of of' would remove all contexts"
                                        " containing double 'of's",
                                   owner_permission=True),
                     PyborgCommand(name="learning",
                                   command_callable=learning,
                                   help="Usage: !learning [on|off]\nToggle bot learning. Without arguments shows the "
                                        "current setting",
                                   owner_permission=True),
                     PyborgCommand(name="censor",
                                   command_callable=censor,
                                   help="Usage: !censor [word1 [...]]\nPrevent the bot using one or more words. "
                                        "Without arguments lists the currently censored words",
                                   owner_permission=True),
                     PyborgCommand(name="uncensor",
                                   command_callable=uncensor,
                                   help="Usage: !uncensor word1 [word2 [...]]\nRemove censorship on one or more words",
                                   owner_permission=True),
                     PyborgCommand(name="quit",
                                   command_callable=quit,
                                   help="Termine the pyborg processus.",
                                   owner_permission=True)]
