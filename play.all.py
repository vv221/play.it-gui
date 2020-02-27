#! /usr/bin/python3
# coding: Utf-8

import os
import json
import time
import signal
import locale
import threading
import webbrowser
import urllib.request

import gi  # Using GTK+
gi.require_version("Gtk", "3.0")
gi.require_version("Vte", "2.91")
from gi.repository import Gtk as gtk
from gi.repository import Vte as vte
from gi.repository import Gio as gio
from gi.repository import GLib as glib
from gi.repository import GdkPixbuf as gdk

# Targets.
api = "http://api.dotslashplay.it/"
img = "https://img.dotslashplay.it/"
www = "https://wiki.dotslashplay.it/"

try:  # Adding localisation for game pages on the wiki.
    www += locale.getlocale()[0].partition("_")[0]+"/"
except AttributeError:  # getlocale() gets None…
    www += "en/"  # Let's use the default…

# Thumbnails directory.
if "XDG_CACHE_HOME" in os.environ:
    cache = os.path.join(os.getenv("XDG_CACHE_HOME"), "play.it", "thumbnails")
else:  # Let's use the default config path…
    cache = os.path.join(os.getenv("HOME"), ".cache", "play.it", "thumbnails")
if not os.path.isdir(cache):
    os.makedirs(cache)

# Main window.
window = gtk.Window()
window.set_title("./play.it")
window.set_size_request(500, 300)
window.set_icon_name("system-software-install")
stack = gtk.Stack()
stack.set_transition_type(gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
window.add(stack)
theme = gtk.IconTheme.get_default()
flags = glib.SpawnFlags.SEARCH_PATH|glib.SpawnFlags.DO_NOT_REAP_CHILD

# Pre-loading some common icons…
loading = theme.load_icon("image-loading", 72, gtk.IconLookupFlags.FORCE_SIZE)
unknown = theme.load_icon("dialog-question", 72, gtk.IconLookupFlags.FORCE_SIZE)
here = "dialog-apply" if theme.has_icon("dialog-apply") else "emblem-default"
here = theme.load_icon(here, 16, gtk.IconLookupFlags.FORCE_SIZE)
able = "filesave" if theme.has_icon("filesave") else "insert-object"
able = theme.load_icon(able, 16, gtk.IconLookupFlags.FORCE_SIZE)
nope = theme.load_icon("dialog-error", 16, gtk.IconLookupFlags.FORCE_SIZE)
browse = theme.load_icon("web-browser", 16, gtk.IconLookupFlags.FORCE_SIZE)

# Adding scrollbars.
def scroll(widget):
    scroll = gtk.ScrolledWindow()
    scroll.set_overlay_scrolling(False)
    scroll.add(widget)
    return scroll

# Connect signals with a decorator.
def listen(gobj, signal):
    def listener(funct):
        gobj.connect(signal, funct)
        return funct
    return listener

# Closing by shortcut (ctrl+q).
@listen(window, "key-press-event")
def shortcut(window, event):
    if stack.get_visible_child_name() != "setup" or play.get_sensitive():
        mask = gi.repository.Gdk.ModifierType.CONTROL_MASK
        if event.keyval in (81, 113) and event.state&mask == mask:
            window.destroy()

# Check for commands.
def launchable(command):
    return any(os.access(os.path.join(folder, command), os.X_OK)
              for folder in os.getenv("PATH").split(os.pathsep))

# First step: game choice.
box = gtk.Box.new(gtk.Orientation.VERTICAL, 0)
search = gtk.Entry()
search.set_icon_from_icon_name(gtk.PackType.END, "web-browser")
search.set_icon_from_icon_name(gtk.PackType.START, "search")
box.pack_start(search, False, False, 0)
games = gtk.ListStore(gdk.Pixbuf, str, int, str, str)
icview = gtk.IconView.new_with_model(games)
icview.set_pixbuf_column(0)
icview.set_text_column(1)
icview.set_item_width(150)
box.pack_start(scroll(icview), True, True, 0)
stack.add_named(box, "list")

# Filtering the game list.
@listen(search, "activate")
@listen(window, "show")
def searching(*args):
    games.clear()
    url = api+"/games/search?search="+urllib.parse.quote(search.get_text())
    if url.endswith("="):  # There's no game here.
        url = api+"/games/list"  # Let's list all.
    url += "&" if "?" in url else "?"
    url += "properties=game_name,game_id,id,images.thumbnail,images.banner"
    with urllib.request.urlopen(url) as f:
        for game in json.loads(f.read()):
            if game["images"]["banner"]["small"] is None:
                # falls back on thumbnail if banner is not provided
                image = game["images"]["thumbnail"]
            else:
                image = game["images"]["banner"]["small"]
            games.append([ loading, game["game_name"], game["id"],
                           game["game_id"], image ])

@listen(search, "icon-press")
def searchicon(search, pos, event):
    if pos == gtk.EntryIconPosition.PRIMARY:
        searching()  # Simple search.
    else:  # Opening the website.
        webbrowser.open(www+"start")

# Selecting the game.
@listen(icview, "item-activated")
def select(icview, path):
    window.set_title(games[path][1])
    stack.set_visible_child_name("details")
    predeps = []
    files.clear()
    url = api+"/games/show/"+str(games[path][2])+"?archives_view=flat"
    with urllib.request.urlopen(url) as f:
        for group in json.loads(f.read())["script"]["archives"]:
            parent = files.append(None, [ None, group[0]["name"],
                                  None, None, None, None, None ])
            for archive in group:
                archive["st"] = None
                archive["br"] = None if archive["url"] is None else browse
                archive["download_links"] = [ archive["download_torrent"],
                                              archive["download_direct"] ]
                while None in archive["download_links"]:
                    archive["download_links"].remove(None)
                files.append(parent, list(archive[key] for key in ("st", "name",
                    "br", "url", "required", "dependencies", "download_links")))
    if len(files) == 1:
        tview.expand_all()
    moving()

# Second step: depandancies listing.
box = gtk.Box.new(gtk.Orientation.VERTICAL, 0)
folder = gtk.Entry()
folder.set_text(os.getcwd())
folder.set_icon_from_icon_name(gtk.PackType.END, "fileopen"
                if theme.has_icon("fileopen") else "folder")
folder.set_icon_from_icon_name(gtk.PackType.START, "folder")
box.pack_start(folder, False, False, 0)
files = gtk.TreeStore(gdk.Pixbuf, str, gdk.Pixbuf, str, bool, object, object)
tview = gtk.TreeView.new_with_model(files)
tview.set_headers_visible(False)
tvc = gtk.TreeViewColumn()
cell = gtk.CellRendererPixbuf()
tvc.pack_start(cell, False)
tvc.add_attribute(cell, "pixbuf", 0)
cell = gtk.CellRendererText()
tvc.pack_start(cell, True)
tvc.add_attribute(cell, "text", 1)
cell = gtk.CellRendererPixbuf()
tvc.pack_start(cell, False)
tvc.add_attribute(cell, "pixbuf", 2)
tview.append_column(tvc)
box.pack_start(scroll(tview), True, True, 0)
line = gtk.Box.new(gtk.Orientation.HORIZONTAL, 0)
back = gtk.Button()
back.set_image(gtk.Image.new_from_icon_name("go-previous", gtk.IconSize.MENU))
line.pack_start(back, True, True, 0)
wiki = gtk.Button()
wiki.set_image(gtk.Image.new_from_icon_name("web-browser", gtk.IconSize.MENU))
wiki.connect("clicked", lambda *args:
    webbrowser.open(www+"games/"+games[icview.get_selected_items()[0]][3]))
line.pack_start(wiki, True, True, 0)
apply = gtk.Button()
apply.set_image(gtk.Image.new_from_icon_name("gtk-execute", gtk.IconSize.MENU))
line.pack_start(apply, True, True, 0)
box.pack_end(line, False, False, 0)
stack.add_named(box, "details")

# Folder choice.
@listen(folder, "activate")
def moving(*args):
    target = folder.get_text()
    if os.path.isdir(target):
        content = os.listdir(target)
        gicon = gio.File.new_for_path(target).query_info("standard::*",
                                gio.FileQueryInfoFlags.NONE).get_icon()
        folder.set_icon_from_gicon(gtk.PackType.START, gicon)
    else:  # Oops, that's not a directory.
        folder.set_icon_from_icon_name(gtk.PackType.START, "binary")
        content = []  # No files here.
    for i in range(len(files)):
        status = 2  # Let's check all files here.
        for j in range(files.iter_n_children(files.get_iter(i))):
            status = min(status, check(content, i, j))
        files[i][2] = (nope, able, here)[status]
    selected(tview.get_selection())

def check(content, *path):
    if files[path][1] in content:
        files[path][0] = here
        return 2
    elif len(files[path][6]) > 0:
        files[path][0] = able
        return 1
    files[path][0] = nope
    return 0

@listen(folder, "icon-press")
def searchicon(search, pos, event):
    if pos == gtk.EntryIconPosition.PRIMARY:
        moving()  # Let's apply this…
    else:  # Using a filechooser…
        dialog = gtk.FileChooserDialog()
        dialog.set_title(window.get_title())
        dialog.set_action(gtk.FileChooserAction.SELECT_FOLDER)
        dialog.add_button(gtk.STOCK_CANCEL, gtk.ResponseType.CANCEL)
        dialog.add_button(gtk.STOCK_OPEN, gtk.ResponseType.OK)
        dialog.set_current_folder(folder.get_text())
        dialog.set_icon_name("fileopen")
        if dialog.run() == gtk.ResponseType.OK:
            folder.set_text(dialog.get_filename())
            moving()
        dialog.destroy()

# Selecting the good candidate.
@listen(tview.get_selection(), "changed")
def selected(tsel):
    it = tsel.get_selected()[1]
    if it is None:
        if len(files) == 1:
            tsel.select_iter(files.get_iter(0))
            return  # We will come back.
        apply.set_sensitive(False)
        return  # Nothing more.
    parent = files.iter_parent(it)
    if parent is not None:
        it = parent  # Moving up.
    apply.set_sensitive(files[it][2] is not nope)

@listen(tview, "focus-out-event")
def selection(*args):
    tsel = tview.get_selection()
    parent = files.iter_parent(tsel.get_selected()[1])
    if parent is not None:
        tsel.select_iter(parent)

# Open a file's url.
@listen(tview, "row-activated")
def select(tview, path, column):
    if files.iter_parent(files.get_iter(path)) is None:
        if tview.row_expanded(path):
            tview.collapse_row(path)
        else:  # Showing the files…
            tview.expand_row(path, False)
    elif files[path][3] is not None:
        webbrowser.open(files[path][3])

# Going back to the list.
@listen(back, "clicked")
def goback(*args):
    window.set_title("./play.it")
    stack.set_visible_child_name("list")

# Generate root command.
def asroot(*command):
    if launchable("sudo"):
        if "SUDO_ASKPASS" in os.environ:
            return ("sudo", "-A")+command
        return ("sudo",)+command
    if command[:2] == ("sh", "-c"):
        return ("su",)+command[1:]
    return "su", "-c", " ".join(command)

# Launching the installation.
@listen(apply, "clicked")
def perform(*args):
    back.set_sensitive(False)
    play.set_sensitive(False)
    stack.set_visible_child_name("setup")
    play.get_image().set_from_pixbuf(None)
    term.spawn_sync(vte.PtyFlags.DEFAULT, folder.get_text(),
                           ("true",), [], flags, None, None)

# Third step: ./play.it!
box = gtk.Box.new(gtk.Orientation.VERTICAL, 0)
term = vte.Terminal()
box.pack_start(scroll(term), True, True, 0)
term.get_parent().set_policy(gtk.PolicyType.NEVER, gtk.PolicyType.ALWAYS)
line = gtk.Box.new(gtk.Orientation.HORIZONTAL, 0)
back = gtk.Button()
back.set_image(gtk.Image.new_from_icon_name("go-previous", gtk.IconSize.MENU))
line.pack_start(back, True, True, 0)
play = gtk.Button()
play.set_image(gtk.Image())
line.pack_start(play, True, True, 0)
box.pack_end(line, False, False, 0)
stack.add_named(box, "setup")

@listen(play, "clicked")
def playit(*args):
    os.system(games[icview.get_selected_items()[0]][3]+" &")
    window.destroy()

# When it's ready…
@listen(term, "child-exited")
def download(term, status):
    it = files.iter_children(tview.get_selection().get_selected()[1])
    while it is not None:
        archive = os.path.join(folder.get_text(), files.get_value(it, 1))
        if not os.path.exists(archive):
            if len(files.get_value(it, 6)) > 0:
                name = files.get_value(it, 1)
                url = files.get_value(it, 6).pop(0)
                term.spawn_sync(vte.PtyFlags.DEFAULT, folder.get_text(),
                              getfile(url, name), [], flags, None, None)
                return  # We will come back with the file.
            if files.get_value(it, 4):
                back.set_sensitive(True)
                return  # No more possible.
        it = files.iter_next(it)
    term.disconnect_by_func(download)
    term.connect("child-exited", build)
    packages, system = listpackages()
    dependencies = set()
    it = files.iter_children(tview.get_selection().get_selected()[1])
    while it is not None:
        requirements = files.get_value(it, 5)
        if system in requirements.keys():
            for entry in requirements[system]:
                p = list(p.partition(" ")[0] for p in entry.split(" | "))
                if not any(package in packages for package in p):
                    dependencies.add(p[0])
        it = files.iter_next(it)
    term.spawn_sync(vte.PtyFlags.DEFAULT, folder.get_text(),
               getdeps(dependencies), [], flags, None, None)

def getfile(url, filename):
    if url.startswith("http") and not url.endswith(".torrent"):
        if launchable("wget"):
            return "wget", url
        if launchable("curl"):
            return "curl", url, "--output", filename
    if launchable("aria2c"):  # Can get torrent too.
        return "aria2c", "--seed-time=0", url
    return ("false",)  # Won't work.

def listpackages():
    if launchable("dpkg-query"):
        with os.popen("dpkg-query -f '${binary:Package}\n' -W") as f:
            return f.read().splitlines(), "debian"
    elif launchable("pacman"):
        with os.popen("pacman -Qq") as f:
            return f.read().splitlines(), "archlinux"
    elif os.path.isdir("/var/db/pkg"):
        if launchable("eix-installed"):
            command = "eix-installed -a"
        else:  # eix is not here. Let's check this manually.
            command = "find /var/db/pkg -mindepth 2 -maxdepth 2 -printf '%P\n'"
        with os.popen(command+" | sed 's/-[0-9].*$//'") as f:
            return f.read().splitlines(), "gentoo"
    return [], None

def getdeps(dependencies):
    if len(dependencies) == 0:
        return ("true",)
    if launchable("apt"):
        return asroot("apt", "install", "--assume-yes", *dependencies)
    if launchable("pacman"):
        return asroot("pacman", "--asdeps", "--noconfirm", "-S", *dependencies)
    if launchable("emerge"):
        return asroot("emerge", "--oneshot", *dependencies)
    return ("false",)

def build(term, status):
    term.disconnect_by_func(build)
    if status == 0:
        term.connect("child-exited", setup)
        it = files.iter_children(tview.get_selection().get_selected()[1])
        term.spawn_sync(vte.PtyFlags.DEFAULT, folder.get_text(),
            ("play.it", files.get_value(it, 1)), [], flags, None, None)
    else:  # Oops, it failed…
        back.set_sensitive(True)
        term.connect("child-exited", download)

def setup(term, status):
    term.disconnect_by_func(setup)
    if status == 0:
        term.connect("child-exited", done)
        last = term.get_text(None)[0].strip().rpartition("\n")[2]
        term.spawn_sync(vte.PtyFlags.DEFAULT, folder.get_text(),
                asroot("sh", "-c", last), [], flags, None, None)
    else:  # Oops, it failed…
        back.set_sensitive(True)
        term.connect("child-exited", download)

def done(term, status):
    back.set_sensitive(True)
    term.disconnect_by_func(done)
    term.connect("child-exited", download)
    if status == 0:  # Done! \o/
        play.set_sensitive(True)
        theme.rescan_if_needed()
        icon = games[icview.get_selected_items()[0]][3]
        play.get_image().set_from_icon_name(icon, gtk.IconSize.MENU)

# Going back to the files.
@listen(back, "clicked")
def goback(*args):
    if play.get_sensitive():
        window.set_title("./play.it")
        stack.set_visible_child_name("list")
    else:  # Something went wrong…
        stack.set_visible_child_name("details")
        moving()

# Image loading thread.
def loadimages():
    while True:
        time.sleep(0.1)
        path, game, url = findnext()
        if path is None:
            continue
        thumb = os.path.join(cache, game)
        if url is not None and not os.path.exists(thumb):
            with urllib.request.urlopen(img+url) as f:
                with open(thumb, "bw") as g:
                    g.write(f.read())
        glib.idle_add(showimage, path, game, thumb)

def showimage(path, game, thumb):
    if path < len(games) and games[path][3] == game:
        if os.path.exists(thumb):
            games[path][0] = gdk.Pixbuf.new_from_file_at_size(thumb, 128, 72)
        elif theme.has_icon(game):
            games[path][0] = theme.load_icon(game, 72,
                       gtk.IconLookupFlags.FORCE_SIZE)
        else:  # Using a fallback icon.
            games[path][0] = unknown

def findnext():
    if stack.get_visible_child_name() == "list":
        bds = icview.get_visible_range()
        bds = (len(games),) if bds is None else (bds[0][0], bds[1][0]+1)
        for i in range(*bds):
            if games[i][0] is loading:
                return i, games[i][3], games[i][4]
    return None, None, None  # All done!

# Ready.
window.show_all()
window.resize(580, 340)
threading.Thread(None, loadimages, daemon=True).start()
glib.unix_signal_add(glib.PRIORITY_HIGH, signal.SIGTERM, gtk.main_quit)
glib.unix_signal_add(glib.PRIORITY_HIGH, signal.SIGINT, gtk.main_quit)
window.connect("destroy", gtk.main_quit)
gtk.main()
