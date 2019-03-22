#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#    Wine Launcher Creator (c) 2011  Žarko Živanov

#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.

#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.

#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

VERSION="1.1.0"

import sys
import glob
import re
import os
import tempfile
import subprocess
import shlex
import shutil
import configparser
import unicodedata
import urllib.request, urllib.parse, urllib.error

from PyQt4.QtGui import *
from PyQt4.QtCore import *

ICON_SIZE = 64

INDEX = 0
WIDTH = 1
HEIGHT = 2
BIT_DEPTH = 3

def getSuffix(file):
    # Windows file system case comparisons convert both sides to upper case.
    # TODO: Use binary headers, not extensions
    return file[-4:].upper()

def iconImages(ico):
    icons = subprocess.check_output(["icotool", "-l", ico])
    if icons and icons[-1] == ord("\n"):
        icons = icons[:-1]
    return [tuple(int(image[key]) for key in [b"index", b"width", b"height", b"bit-depth"])
            for image
            in (dict(re.findall(b"--([^ =]*)(?:=([^ ]*))?", image)) for image in icons.split(b"\n"))]

def iconExtract(ico, image, path):
    #convert ico file to png files

    # icotool is a bit broken with Windows 7 explorer.exe.
    subprocess.check_call(
        [
            "icotool",
            "-x",
            "--icon",
            "--index",
            str(image[INDEX]),
            ico
        ],
        cwd = path)

    if getSuffix(ico) == ".ICO":
        ico = ico[:-4]

    return "{}_{}_{}x{}x{}.png".format(
        os.path.join(path, os.path.basename(ico)),
        image[INDEX],
        image[WIDTH],
        image[HEIGHT],
        image[BIT_DEPTH])

def multiIconFile(suffix):
    return suffix in [".EXE", ".DLL", ".ICL"]

def check_output(*popenargs, **kwargs):
    """This function is copied from python 2.7.1 subprocess.py
       Copyright (c) 2003-2005 by Peter Astrand <astrand@lysator.liu.se>
       Licensed to PSF under a Contributor Agreement.
       See http://www.python.org/2.4/license for licensing details."""
    if 'stdout' in kwargs:
        raise ValueError('stdout argument not allowed, it will be overridden.')
    process = subprocess.Popen(stdout=subprocess.PIPE, stderr=subprocess.STDOUT, *popenargs, **kwargs)
    output, unused_err = process.communicate()
    retcode = process.poll()
    if retcode:
        cmd = kwargs.get("args")
        if cmd is None:
            cmd = popenargs[0]
        raise CalledProcessError(retcode, cmd, output=output)
    return output

def bash(command, workdir=None):
    """Helper function to execute bash commands"""
    #command = shlex.split(command.encode("utf-8"))
    print("COMMAND:",command)
#    try:
#        code = subprocess.call(command, stderr=subprocess.STDOUT, stdout=subprocess.PIPE, cwd=workdir)
#    except:
#        code = 127
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   shell=True, cwd=workdir)
        output, unused_err = process.communicate()
        output = output.decode("utf-8")
        code = process.poll()
    except:
        code = 127
    if len(output) > 0: print("OUTPUT:\n",output,sep="")
    print("CODE:",code)
    return code,output

def checkDependencies():
    """Helper function to check for icoutils"""
    missing = False
    missingText = ""
    #check icoutils
    code,output = bash("wrestool --version")
    if code > 0:
        if missingText != "":
            missingText += "\n"
        missingText += "Missing dependencie: icoutils"
        missing = True
    if missing:
        dialog = QMessageBox(QMessageBox.Critical,"Missing dependencies",missingText)
        dialog.exec_()
    return not missing

class BrowseControl(QHBoxLayout):
    """Control containing label, edit field and button
       Used to browse for files and directories"""
    def __init__(self, label, browseTitle, toolTip, defaultPath, callback=None,
                 extensions="", browseDirectory=False, setStatus=None, showHidden=False,
                 oneUp = False, parent=None):
        super(BrowseControl, self).__init__(parent)

        #control's label
        self.label = QLabel(label+":")
        self.addWidget(self.label)
        #control's edit
        self.edit = QLineEdit()
        self.addWidget(self.edit,1)
        self.edit.setToolTip(toolTip)
        self.connect(self.edit, SIGNAL("textChanged(QString)"), self.edited)
        #control's up button
        if oneUp:
            self.uButton = QPushButton("Up")
            self.addWidget(self.uButton)
            self.uButton.setToolTip("Go one level up")
            self.connect(self.uButton, SIGNAL("clicked()"), self.oneUp)
        #control's browse button
        self.button = QPushButton("Browse")
        self.addWidget(self.button)
        self.button.setToolTip("Select new "+label)
        self.connect(self.button, SIGNAL("clicked()"), self.browse)
        #control's default button
        if defaultPath != "":
            self.dButton = QPushButton("Default")
            self.addWidget(self.dButton)
            self.dButton.setToolTip("Reset "+label+" to '"+defaultPath+"'")
            self.connect(self.dButton, SIGNAL("clicked()"), self.default)

        #function to call after successful change of path
        self.callback = callback
        #text for file dialog
        self.browseTitle = browseTitle
        #allowed extensions
        self.extensions = extensions
        #select file or directory
        self.browseDirectory = browseDirectory
        #show or hide hidden files
        self.showHidden = showHidden
        #function for setStatus display
        self.setStatus = setStatus
        #text for invalid path
        self.setStatusNotValid = label+" not valid!"
        #python string containing selected path
        self.path = ""
        #should callback be called
        self.noCallback = False
        #is path valid
        self.pathValid = True
        #default path
        self.defaultPath = defaultPath

    def browse(self):
        """callback for Browse button"""
        if self.browseDirectory:
            #dialog for selecting directories
            dialog = QFileDialog(None,self.browseTitle,self.edit.text())
            dialog.setFileMode(QFileDialog.Directory)
            if self.showHidden:
                dialog.setFilter(QDir.AllEntries | QDir.Hidden )
        else:
            #dialog for selecting files
            dialog = QFileDialog(None,self.browseTitle,os.path.dirname(self.path),self.extensions)
            if self.pathValid:
                dialog.selectFile(self.path)
            dialog.setFileMode(QFileDialog.ExistingFile)
        dialog.setAcceptMode(QFileDialog.AcceptOpen)
        if dialog.exec_() == QDialog.Accepted:
            #if user selected something
            self.path = str(dialog.selectedFiles()[0])
            self.pathValid = True
            self.noCallback = True
            self.edit.setText(self.path)
            self.noCallback = False
            if self.setStatus != None: self.setStatus()
            if self.callback != None: self.callback()

    def edited(self):
        """callback for edit control"""
        self.path = str(self.edit.text())
        self.pathValid = os.access(self.path, os.F_OK)
        if self.pathValid:
            if self.setStatus != None: self.setStatus()
        else:
            if self.setStatus != None: self.setStatus(self.setStatusNotValid + "('"+self.path+"' doesn't exist)")
            return
        if self.noCallback: return
        elif self.callback != None: self.callback()

    def default(self):
        self.edit.setText(self.defaultPath)

    def oneUp(self):
        self.edit.setText(os.path.dirname(self.path))

class EditControl(QHBoxLayout):
    """control containing label and edit control"""
    def __init__(self, label, toolTip, callback=None, parent=None): 
        super(EditControl, self).__init__(parent)

        #control's label
        self.label = QLabel(label+":")
        self.addWidget(self.label)
        #control's edit
        self.edit = QLineEdit()
        self.addWidget(self.edit,1)
        self.callback = callback
        self.edit.setToolTip(toolTip)
        self.connect(self.edit, SIGNAL("textChanged(QString)"), self.edited)
        self.text = ""

    def edited(self):
        """callback for edit control"""
        self.text = str(self.edit.text())
        if self.callback != None: self.callback()

class DebugDialog(QDialog):
    def __init__(self, name, command, parent=None):
        super(DebugDialog, self).__init__(parent)
        self.setWindowTitle('Output when launching "'+name+'"')
        self.resize(700,700)
        self.layout = QVBoxLayout()
        self.debugOutput = QTextEdit()
        self.layout.addWidget(self.debugOutput)
        self.setLayout(self.layout)
        self.command = command

    def debug(self):
#        process = subprocess.Popen(self.command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)
#        output, unused_err = process.communicate()
#        retcode = process.poll()
        code,output = bash(self.command)
        self.debugOutput.setPlainText(output)

class WaitDialog(QDialog):
    def __init__(self, parent=None):
        super(WaitDialog, self).__init__(parent)
        self.setWindowTitle('Please wait...')

class MainWindow(QMainWindow):
    """main application window"""
    def __init__(self, parent=None): 
        super(MainWindow, self).__init__(parent)

        #user's desktop location
        self.desktopPath = check_output(["xdg-user-dir", "DESKTOP"]).decode("utf-8")
        while self.desktopPath[-1] == "\n": self.desktopPath = self.desktopPath[:-1]

        #default config options
        self.cfgDefaults = {'Launcher': self.desktopPath,
                            'Icons': os.path.expanduser("~/.local/share/icons/wlcreator"),
                            'Wine': "wine",
                            'WinePrefix': os.path.expanduser("~/.wine"),
                            'Bottles': os.path.expanduser("~/")}

        self.setWindowTitle("Wine Launcher Creator")
        self.setWindowIcon(QIcon.fromTheme('wine'))

        self.centralWidget = QWidget()
        self.centralWidgetLayout = QVBoxLayout()
        self.centralWidget.setLayout(self.centralWidgetLayout)
        self.setCentralWidget(self.centralWidget)

        self.statusBar = QStatusBar(self)
        self.statusBar.setObjectName("setStatusbar")
        self.setStatusBar(self.statusBar)

        #widget containing main interface
        self.widget1 = QWidget()
        self.layout1 = QVBoxLayout()
        self.layout1.setAlignment(Qt.AlignTop)
        self.widget1.setLayout(self.layout1)
        self.centralWidgetLayout.addWidget(self.widget1)

        self.executable = BrowseControl("Exe path", "Select exe file", "Path to an Windows executable file", "",
            self.exeCallback, "exe (*.exe *.EXE)", setStatus=self.setStatus)
        self.layout1.addLayout(self.executable)

        self.appParams = EditControl("Application parameters","Additional parameters that need to be sent to application")
        self.layout1.addLayout(self.appParams)

        self.application = BrowseControl("Toplevel app path", "Select toplevel application path", "Path to application's toplevel directory"+
            "\n(used to search for additional ico/png files and to guess application name)", "",
            self.appCallback, browseDirectory=True, setStatus=self.setStatus, oneUp = True)
        self.layout1.addLayout(self.application)

        self.name = EditControl("Name","Launcher's name")
        self.layout1.addLayout(self.name)

        # Not included: the rarely seen *.icl.
        self.iconPath = BrowseControl("Icon", "browseTitle",
            "Path to the file containing the icon. Often this is just the executable.", "", self.iconCallback,
            "All supported icons (*.ico *.ICO *.exe *.EXE *.dll *.DLL *.png *.PNG *.svg *.SVG)")
        self.layout1.addLayout(self.iconPath)

        self.iconWidget = QListWidget()
        self.layout1.addWidget(self.iconWidget)
        self.iconWidget.setViewMode(QListView.IconMode)
        self.iconWidget.setMovement(QListView.Static)
        self.iconWidget.setResizeMode(QListView.Adjust)

        # Desktop icon size, more-or-less, judging by Kubuntu and Debian screenshots.
        # https://cgit.kde.org/kiconthemes.git/tree/src/kicontheme.cpp hints that it's normally 32, but that seems wrong.
        # QApplication.style().pixelMetric(QStyle.PM_MessageBoxIconSize) is another option.
        self.iconWidget.setIconSize(QSize(ICON_SIZE,ICON_SIZE))
        
        self.prefix = BrowseControl("Wine prefix path", "Select Wine prefix path", 
            "Path to directory containing Wine prefix (bottle)", self.cfgDefaults['WinePrefix'],
            browseDirectory=True, setStatus=self.setStatus, showHidden=True)
        self.layout1.addLayout(self.prefix)

        #bottle adminsitration
        layout = QHBoxLayout()
        self.layout1.addLayout(layout)

        button = QPushButton("Select launcher's name as prefix")
        layout.addWidget(button)
        button.setToolTip("Select new Wine prefix (bottle) in default prefix directory,\nor use existing if prefix already exists.\nUses same name as the launcher name.")
        self.connect(button, SIGNAL("clicked()"), self.selectPrefix)

        button = QPushButton("Launch WineCfg/Populate prefix files")
        layout.addWidget(button)
        button.setToolTip("Launch WineCfg for selected Wine prefix\nand populate with wine files if necessary")
        self.connect(button, SIGNAL("clicked()"), self.winecfg)

        button = QPushButton("Launch WineTricks")
        layout.addWidget(button)
        button.setToolTip("Launch WineTricks for selected Wine prefix")
        self.connect(button, SIGNAL("clicked()"), self.winetricks)

        #fix layout
        layout = QHBoxLayout()
        self.layout1.addLayout(layout)

        self.win32Prefix = QCheckBox("Create WIN32 Prefix")
        layout.addWidget(self.win32Prefix)
        self.win32Prefix.setToolTip("Add WINEARCH=win32 when calling winecfg for new prefix")
        self.win32Prefix.setCheckState(Qt.Unchecked)

        self.resolutionFix = QCheckBox("Restore resolution")
        layout.addWidget(self.resolutionFix)
        self.resolutionFix.setToolTip("Add 'xrandr -s 0' at the end of command line\nto force native resolution after the application exits")
        self.resolutionFix.setCheckState(Qt.Unchecked)

        self.legacyFS = QCheckBox("Compiz Legacy Fullscreen Support")
        layout.addWidget(self.legacyFS)
        self.legacyFS.setToolTip("Turno on Compiz Legacy Fullscreen Support before starting the application\n(fix for Ubuntu 12.04 LTS)")
        self.legacyFS.setCheckState(Qt.Unchecked)

        self.debug = QPushButton("Debug launching")
        layout.addWidget(self.debug)
        self.debug.setToolTip("Try to launch the application,\nand show command line output after it finishes")
        self.connect(self.debug, SIGNAL("clicked()"), self.debugLauncher)

        #always visible buttons
        layout = QHBoxLayout()
        self.centralWidgetLayout.addLayout(layout)

        button = QPushButton("Settings")
        self.settings = button
        button.setCheckable(True)
        layout.addWidget(button)
        self.connect(button, SIGNAL("clicked()"), self.settingsToggle)

        button = QPushButton("Create exe launcher")
        layout.addWidget(button,1)
        self.connect(button, SIGNAL("clicked()"), self.createLauncher)

        button = QPushButton("About")
        layout.addWidget(button)
        self.connect(button, SIGNAL("clicked()"), self.about)

        #widget containing options interface
        self.widget2 = QWidget()
        self.layout2 = QVBoxLayout()
        self.layout2.setAlignment(Qt.AlignTop)
        self.widget2.setLayout(self.layout2)
        self.centralWidgetLayout.addWidget(self.widget2)
        self.widget2.hide()

        self.launcher = BrowseControl("Launcher path", "Select launcher path",
            "Path to directory for launcher creation", self.cfgDefaults['Launcher'],
            browseDirectory=True, setStatus=self.setStatus)
        self.layout2.addLayout(self.launcher)

        self.bottles = BrowseControl("Default Wine prefixes (bottles) path", "Select default wine bottles path",
            "Path to directory for wine prefixes (bottles) creation", self.cfgDefaults['Bottles'],
            browseDirectory=True, setStatus=self.setStatus)
        self.layout2.addLayout(self.bottles)

        self.wine = EditControl("Wine command", "Command used to run Windows applications")
        self.layout2.addLayout(self.wine)

        button = QPushButton("Install Wine Launcher Creator as Gnome 2 Nautilus Action")
        self.layout2.addWidget(button)
        self.connect(button, SIGNAL("clicked()"), self.nautilus2Action)

        button = QPushButton("Install Wine Launcher Creator as Gnome 3 Nautilus Action")
        self.layout2.addWidget(button)
        self.connect(button, SIGNAL("clicked()"), self.nautilus3Action)

        button = QPushButton("Install Wine Launcher Creator as Nautilus Script")
        self.layout2.addWidget(button)
        self.connect(button, SIGNAL("clicked()"), self.nautilusScript)

        button = QPushButton("Install Wine Launcher Creator as KDE 4 Dolphin Service menu")
        self.layout2.addWidget(button)
        self.connect(button, SIGNAL("clicked()"), self.dolphinMenu)

        label = QLabel("""Additional information about restricting internet access to (untrusted) (Windows)
            <br>application can be found in /usr/local/share/wlcreator/NoInternet.txt""")
        label.setTextFormat(Qt.RichText)
        self.layout2.addWidget(label)

        button = QPushButton("Open NoInternet.txt")
        self.layout2.addWidget(button)
        self.connect(button, SIGNAL("clicked()"), self.openNoInternet)

        button = QPushButton("Revert all settings to default values")
        self.layout2.addWidget(button)
        self.connect(button, SIGNAL("clicked()"), self.defaultConfig)

        #temorary directory for icon extraction
        self.temporary = tempfile.mkdtemp(prefix = 'wlcreator-')
        #first argument is path to exe file
        path = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else ""
        path = urllib.parse.unquote(path)
        self.executable.edit.setText(path)
        #second argument is path to main application directory (ico files search path/initial name guess)
        path = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else os.path.dirname(self.executable.path)
        path = urllib.parse.unquote(path)
        self.application.edit.setText(path)

        #directory for program's configuration file
        self.config = os.path.expanduser("~/.config/wlcreator")
        self.loadConfig()

        self.resize(QSize(700,600))
        if self.executable.path == "": self.setStatus("Select an exe file.")

    def cleanup(self):
        """executed at the end"""
        self.saveConfig()
        self.clearTemporary()
        os.rmdir(self.temporary)

    def clearTemporary(self):
        """removes all files in temporary directory"""
        if self.temporary != "":
            fileList = glob.glob( os.path.join(self.temporary, '*.*') )
            for f in fileList:
                os.remove(f)

    def setStatus(self,text=None):
        """display of setStatus text"""
        if text == None: text = "OK."
        self.statusBar.showMessage(text)

    def exeCallback(self):
        """callback for executable path"""
        exePath = self.executable.path
        path = os.path.dirname(exePath)
        self.application.edit.setText(path)
        self.iconPath.edit.setText(exePath)

    def iconCallback(self):
        self.populateIconList(self.iconPath.path)

    def appCallback(self):
        """callback for application path"""
        self.name.edit.setText(os.path.basename(self.application.path))

    def selectPrefix(self):
        path = os.path.join(self.bottles.path,self.name.text)
        self.prefix.edit.setText(path)

#    def createPrefix(self):
#        self.setStatus("Creating new prefix...")
#        if not os.access(self.prefix.path, os.F_OK):
#            os.makedirs(self.prefix.path)
#        if not os.access(os.path.join(self.prefix.path,"user.reg"), os.F_OK):
#            s1 = " WINEARCH=win32" if self.win32Prefix.isChecked() else ""
#            bash("env" + s1 + " WINEPREFIX=\""+self.prefix.path+"\" wineboot")
#            self.setStatus("New prefix is created in \'"+self.prefix.path+"\'")
#        else:
#            self.setStatus("Prefix alredy populated in \'"+self.prefix.path+"\'")

    def winecfg(self):
        self.setStatus("Launching winecfg...")
#        if not os.access(self.prefix.path, os.F_OK):
#            os.makedirs(self.prefix.path)
        s1 = " WINEARCH=win32" if self.win32Prefix.isChecked() else ""
        bash("env" + s1 + " WINEPREFIX=\""+self.prefix.path+"\" winecfg")
        self.setStatus("Winecfg has finished")

    def winetricks(self):
        self.setStatus("Launching winetricks...")
        if os.access(os.path.join(self.prefix.path,"user.reg"), os.F_OK):
            bash("env WINEPREFIX=\""+self.prefix.path+"\" winetricks")
            self.setStatus("Winetricks has finished")
        else:
            self.setStatus("Prefix \'"+self.prefix.path+"\' not populated. Run WineCfg first.")

    def debugLauncher(self):
        exeDirectory = os.path.dirname(self.executable.path)
        s1 = "  ; xrandr -s 0" if self.resolutionFix.isChecked() else ""
        s2 = "gconftool -s /apps/compiz-1/plugins/workarounds/screen0/options/legacy_fullscreen -s false -t bool ; "  if self.legacyFS.isChecked() else ""
        s3 = " ; gconftool -s /apps/compiz-1/plugins/workarounds/screen0/options/legacy_fullscreen -s false -t bool"  if self.legacyFS.isChecked() else ""
        s4 = " " + self.appParams.text if self.appParams.text != "" else ""
        command = s2 + "cd \"" + exeDirectory + "\"; env WINEPREFIX=\"" + self.prefix.path + \
                  "\" " + self.wine.text + " \"" + self.executable.path + "\"" + s4 + s1 + s3
        dialog = DebugDialog(self.name.text, command)
        dialog.setModal(True)
        dialog.debug()
        dialog.exec_()

    def extractIcoFile(self, ico):
        images = iconImages(ico)

        # (image[WIDTH] + image[HEIGHT]) * 0.5 would also work. There's no wrong answer; XDG just says "size".
        # <https://standards.freedesktop.org/icon-theme-spec/latest/ar01s05.html>
        _, bestWidth, bestHeight, _ = min(images, key = lambda image: abs((image[WIDTH] * image[HEIGHT]) ** 0.5 - ICON_SIZE))

        return iconExtract(
            ico,
            max((image for image in images if image[WIDTH] == bestWidth and image[HEIGHT] == bestHeight),
                key = lambda image: image[BIT_DEPTH]),
            self.temporary)

    def addIcon(self, png, title):
        #insert png file in iconWidget

        # QPixmap can (sometimes) load .ico files, but it will just do the first image, not the best image.
        pixmap = QPixmap(png)
        icon = QIcon(pixmap)
        widget = QListWidgetItem(icon,title)
        widget.setToolTip("Width:"+str(pixmap.width())+"\nHeight:"+str(pixmap.height())+"\nDepth:"+str(pixmap.depth()))
        self.iconWidget.addItem(widget)

        self.setStatus("Icons extracted/found. Select one.")

    def populateIconList(self, iconPath):
        """extracts and finds all icons for specified icon file"""
        self.iconWidget.clear()
        self.clearTemporary()
        extractedList = None

        suffix = getSuffix(iconPath)
        if multiIconFile(suffix):
            #extract icons from exe file
            bash("wrestool -x -t 14 -o \"" + self.temporary + "\" \"" + iconPath + "\"")
            #check if there are any icon files
            if len(os.listdir(self.temporary)) == 0:
                self.setStatus("Could not extract/find any icons! Try using wrestool manually.")
                return

            prefixSize = len(os.path.basename(iconPath)) + 4

            icoList = glob.glob(os.path.join(self.temporary, "*.ico"))
            if not icoList:
                self.setStatus("Could not convert ico(s) to png(s)! Try using icotool manually, or try GIMP.")
                return

            for ico in icoList:
                title = os.path.basename(ico)[prefixSize:][:-4]
                ico_path = os.path.join(self.temporary, title + ".ico")
                png_path = os.path.join(self.temporary, title + ".png")
                os.rename(ico, ico_path)
                #move all found png files from the application directory
                os.rename(self.extractIcoFile(ico_path), png_path)
                self.addIcon(png_path, title)
        elif suffix == ".ICO":
            self.addIcon(self.extractIcoFile(iconPath), os.path.basename(iconPath))
        else:
            self.addIcon(iconPath, os.path.basename(iconPath))

    def createLauncher(self):
        """creates .desktop file"""
        if not self.executable.pathValid: return
        if not self.application.pathValid: return
        #full path to selected icon
        iconSource = self.iconPath.path
        suffix = getSuffix(iconSource)
        if multiIconFile(suffix):
            #get selected icon
            items = self.iconWidget.selectedItems()
            if len(items) == 0:
                self.setStatus("You need to select an icon first.")
                return
            iconSource = os.path.join(self.temporary, items[0].text() + ".ico")

        suffix = getSuffix(iconSource)
        if suffix == ".ICO":
            images = iconImages(iconSource)
            images.sort(key = lambda image: (image[WIDTH], image[HEIGHT], -image[BIT_DEPTH]))

            iconPathBase = os.path.expanduser("~/.local/share/icons/hicolor")
            iconDestination = "wlcreator-" + "".join(
                (c.lower() if c.isalnum() and ord(c) < 0x80 or c in ["_", "."] else "-")
                for c
                in unicodedata.normalize('NFKD', os.path.basename(self.name.edit.text()))
                if not unicodedata.combining(c))

            prev = None
            for image in images:
                if not prev or image[WIDTH] != prev[WIDTH] or image[HEIGHT] != prev[HEIGHT]:
                    iconPath = os.path.join(iconPathBase, "{}x{}".format(image[WIDTH], image[HEIGHT]), "apps")
                    #create icons directory, if it doesn't exist
                    os.makedirs(iconPath, exist_ok = True)
                    #move icon file
                    shutil.move(
                        iconExtract(iconSource, image, path = self.temporary),
                        os.path.join(iconPath, iconDestination + ".png"))
                prev = image

            subprocess.call(["xdg-icon-resource", "forceupdate"])
        else:
            iconDestination = iconSource

        #directory of exe file
        exeDirectory = os.path.dirname(self.executable.path)
        #generate launcher's contents
        launcherText = "#!/usr/bin/env xdg-open\n\n"
        launcherText += "[Desktop Entry]\n"
        launcherText += "Type=Application\n"
        launcherText += "Version=1.0\n"
        launcherText += "Name=" + self.name.text + "\n"
        launcherText += "Icon=" + iconDestination + "\n"
        s1 = "  ; xrandr -s 0" if self.resolutionFix.isChecked() else ""
        s2 = "gconftool -s /apps/compiz-1/plugins/workarounds/screen0/options/legacy_fullscreen -s false -t bool ; "  if self.legacyFS.isChecked() else ""
        s3 = " ; gconftool -s /apps/compiz-1/plugins/workarounds/screen0/options/legacy_fullscreen -s false -t bool"  if self.legacyFS.isChecked() else ""
        s4 = " " + self.appParams.text if self.appParams.text != "" else ""
        launcherText += "Exec=sh -c \"" + s2 + "env WINEPREFIX=\'" + self.prefix.path + "\' " + \
                        self.wine.text + " \'" + self.executable.path + "\'" + s4 + s1 + s3 + "\"\n"
        launcherText += "Path=" + exeDirectory + "\n"
        #full path to launcher
        launcherPath = os.path.join(self.launcher.path, self.name.text+".desktop")
        #write launcher's contents
        launcherFile = open(launcherPath, "w")
        launcherFile.write(launcherText)
        launcherFile.close()
        #make it executable
        bash("chmod 755 \"" + launcherPath + "\"")
        launcherLocalAppPath = os.path.expanduser("~/.local/share/applications/wlcreator/")
        if not os.access(launcherLocalAppPath, os.F_OK):
            os.makedirs(launcherLocalAppPath)
        launcherLocalAppPath = os.path.join(launcherLocalAppPath, self.name.text+".desktop")
        if launcherPath != launcherLocalAppPath:
            shutil.copyfile(launcherPath,launcherLocalAppPath)
            bash("chmod 755 \"" + launcherLocalAppPath + "\"")
            self.setStatus("Launcher created in "+self.launcher.path+". A copy is also in ~/.local/share/applications/wlcreator/")
        else:
            self.setStatus("Launcher created in "+self.launcher.path)

    def defaultConfig(self):
        """creates default configuration options"""
        self.launcher.edit.setText(self.cfgDefaults['Launcher'])
        self.wine.edit.setText(self.cfgDefaults['Wine'])
        self.prefix.edit.setText(self.cfgDefaults['WinePrefix'])
        self.bottles.edit.setText(self.cfgDefaults['Bottles'])

    def loadConfig(self):
        """load configuration options"""
        cfgfile = os.path.join(self.config,"settings.ini")
        cfgRead = False
        if os.access(cfgfile, os.F_OK):
            #if config exists, load it
            cfg = configparser.SafeConfigParser(self.cfgDefaults)
            cfg.read(cfgfile)
            if "WLCreator" in cfg.sections():
                self.launcher.edit.setText(cfg.get("WLCreator","Launcher"))
                self.wine.edit.setText(cfg.get("WLCreator","Wine"))
                self.prefix.edit.setText(cfg.get("WLCreator","WinePrefix"))
                self.bottles.edit.setText(cfg.get("WLCreator","Bottles"))
                cfgRead = True
        if not cfgRead:
            self.defaultConfig()

    def saveConfig(self):
        """save configuration options"""
        #create config directory, if it doesn't exist
        if not os.access(self.config, os.F_OK):
            os.makedirs(self.config)
        cfgfile = open(os.path.join(self.config,"settings.ini"),"w")
        cfg = configparser.SafeConfigParser()
        if not cfg.has_section("WLCreator"):
            cfg.add_section("WLCreator")
        cfg.set("WLCreator","Launcher",self.launcher.path)
        cfg.set("WLCreator","Wine",self.wine.text)
        cfg.set("WLCreator","WinePrefix",self.prefix.path)
        cfg.set("WLCreator","Bottles",self.bottles.path)
        cfg.write(cfgfile)

    def settingsToggle(self):
        """toggle between main interface and options"""
        if self.settings.isChecked():
            self.widget1.hide()
            self.statusBar.hide()
            self.widget2.show()
        else:
            self.widget1.show()
            self.statusBar.show()
            self.widget2.hide()

    def nautilus2Action(self):
        bash("gconftool-2 --load /usr/local/share/wlcreator/wlcaction.xml")

    def nautilus3Action(self):
        path = os.path.expanduser("~/.local/share/file-manager/actions/")
        bash("mkdir -p " + path)
        bash("cp /usr/local/share/wlcreator/wlcreatorGnome.desktop " + path)

    def nautilusScript(self):
        path = os.path.expanduser("~/.gnome2/nautilus-scripts/")
        bash("mkdir -p " + path)
        bash("ln -s /usr/local/bin/wlcreator.py " + path + "/Wine\ Launcher\ Creator")

    def dolphinMenu(self):
        path = os.path.expanduser("~/.kde4/share/kde4/services/ServiceMenus/")
        bash("mkdir -p " + path)
        bash("cp /usr/local/share/wlcreator/wlcreatorKDE.desktop " + path)
        #alternative path; probably can be deleted
        path = os.path.expanduser("~/.kde/share/kde4/services/ServiceMenus/")
        bash("mkdir -p " + path)
        bash("cp /usr/local/share/wlcreator/wlcreatorKDE.desktop " + path)

    def openNoInternet(self):
        bash("xdg-open /usr/local/share/wlcreator/NoInternet.txt")

    def about(self):
        """displays about dialog"""
        text = "Wine Launcher Creator v"+VERSION+" (c) 2011  Žarko Živanov"
        text += "<br>E-Mail: zzarko@gmail.com"
        text += "<br><br>University of Novi Sad, Faculty Of Technical Sciences"
        text += "<br>Chair for Applied Computer Science"
        text += ', <a href="http://www.acs.uns.ac.rs/">http://www.acs.uns.ac.rs</a>'
        text += "<br><br>Linux User Group of Novi Sad"
        text += ', <a href="http://www.lugons.org/">http://www.lugons.org/</a>'

        gpl = "<br><br>This program is free software: you can redistribute it and/or modify"
        gpl += "it under the terms of the GNU General Public License as published by"
        gpl += "the Free Software Foundation, either version 3 of the License, or"
        gpl += "(at your option) any later version."
        gpl += "<br><br>This program is distributed in the hope that it will be useful,"
        gpl += "but WITHOUT ANY WARRANTY; without even the implied warranty of"
        gpl += "MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the"
        gpl += "GNU General Public License for more details."
        gpl += "<br><br>You should have received a copy of the GNU General Public License"
        gpl += "along with this program. If not, see "
        gpl += "<a href=http://www.gnu.org/licenses>http://www.gnu.org/licenses</a>."

        dialog = QMessageBox(QMessageBox.Information,"About",text+gpl)
#        dialog.setInformativeText(gpl)
        dialog.setTextFormat(Qt.RichText)
        dialog.exec_()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    if checkDependencies():
        main = MainWindow()
        main.show()
        app.exec_()
        main.cleanup()

"""
History of changes

Version 1.1.0
    - Requires Python 3. String fixes here and there.
    - More descriptive temp directory name.
    - Icon size in view reduced to 64x64.
    - Replaced recursive search for icons with a single source file for icons + a browse button.
    - View only shows one image from Windows icons.
    - Windows icons are split up by size and placed in ~/.local/share/icons/hicolor/WxH.
    - PNG and SVG icons are left in their original location.
    - Icon images are never placed in the app directory.
    - xdg-icon-resource forceupdate
    - Added newline to end of .desktop.
    - Desktop entry keys are in the same order as the standard.

Version 1.0.8
    - Added option for xrandr -s 0 (wrong resolution after exit fix)
    - Added option to enable legacy Fullscreen Support under Compiz (fix for Ubuntu 12.04 LTS)
    - Added button to go one level up for top level directory
    - Added option to create WIN32 prefix when calling winecfg
    - Added edit box to enter additional parameters when calling exe

Version 1.0.7
    - Fixed handling of spaces in exe file path
    - Added button to create new Wine bottle/prefix
    - Added buttons to launch WineCfg and WineTricks
    - Added setting for default wine bottle path
    - Program now analyses all exe files in given exe file directory
    - Help is shown for browse control buttons
    - Added launching programs and watching output, for debugging

Version 1.0.6
    - Fix for missing 'WLCreator' section in config file
    - Makefile doesn't create '/usr/share/nautilus-scripts/Wine Launcher Creator' anymore
    - Makefile gets program version from wlcreator.py
    - Readme was made better, program page on google also
    - Added button to reset configuration options
    - Fixed png from ico extraction
    - Fixed file copy for integration into gnome/kde
    - Main window made a slightly wider

Version 1.0.5
    - Added Wine prefix setting and changed Exec part of the launcher to include it
    - Default icons path changed to ~/.local/share/icons/wlcreator/
    - gpl text in About dilaog converted to RichText
    - Added program icon - I used 'Wine' icon, as I'm no artist - any contribution is welcome
    - Added various ways to install in Nautilus and Dolphin directly from GUI
    - Added wlcreator.desktop and wlcreatorKDE.desktop for Nautilus 3 and Dolphin integration
    - Removed ImageMagick dependency from deb file
"""

