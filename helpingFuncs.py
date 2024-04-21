# -*- coding: utf-8 -*-

import datetime as dt
import logging

from time import time as timestamp
import os
import sys

from helpingClasses import SrcFile, DestFile, SrcDir

logger = logging.getLogger(f"main.{__name__}")

def invInput(c):
    print("Invalid input, refer to help:\n    ", c, "-h or --help")
    print()
    sys.exit(-1) # -1 error code for invalid input

def printHelp():
    print("Peridocally synchronizes the content of a source ", end='')
    print("directory into a destination directory.")
    print("Logs creation/move/copy/remove operations to console and ", end='')
    print("specified file. Additionally, the file logs debug information.")
    print("Note that the user input validations are not logged.")
    print("Generally, the log file should not be located in the ", end='')
    print("source or replica directories, as well as source cannot ", end='')
    print("be located in replica and vice versa ", end='')
    print("(or each other parent/children directories).", end='')
    print()
    print("  Usage:", sys.argv[0], "--src DIRECTORY ", end='')
    print("--dest DIRECTORY ", end='')
    print("--syncPeriod INTEGER_NUMBER --logFile FILE")
    print()
    print("    --src DIRECTORY, the absolute path of the source directory")
    print("    --dest DIRECTORY, the absolute path to the replica directory")
    print("    --syncPeriod INTEGER_NUMBER, duration of sync cycle (seconds)")
    print("    --logFile FILE, path to log file - file will be overwritten!")
    sys.exit(0)

def validateInput(av):
    '''Validates command line arguments, refer to printHelp for
    details. Creates the dest dir, if it doesn't exist.
    Returns a tuple of the values (sourceDirAbsPath, destinationDirAbsPath,\
                                   syncPeriod, logFilePath, destDirCreatedNow)
    '''
    # validating pre-defined args
    c = av[0] # invoked as command 'c'
    # validating number of arguments
    if len(av) != 9:
        print("Number of arguments incorrect.")
        invInput(c)
    mandatoryArgs = ["--dest", "--logFile", "--src", "--syncPeriod"] # sorted
    # validating arguments, hard-coded ones should be at odd indices:
    cmdArgs = sorted([av[i] for i in range(1, 9, 2)])
    if cmdArgs != mandatoryArgs:
        print("Mandatory arguments supplied incorrectly")
        invInput(c)

    # extracting user input - find at which index a mandator arg is
    # and return the elementent having the following index
    dest, logF, src, p = map((lambda v: av[av.index(v)+1]), mandatoryArgs)
    src = os.path.normpath(src)
    dest = os.path.normpath(dest)
    logF = os.path.normpath(logF)

    # validate user input:
    # log file: location exists and file can be written to
    try:
        logFileLocation = os.path.split(logF)[0]
        logFileLocation = os.path.realpath(logFileLocation, strict=True)
    except:
        print("Log file directory doesn't exist")
        sys.exit(-1)
    try:
        with open(logF, 'w'):
            pass
    except:
        print("Supplied log file path cannot be written to")
        sys.exit(-1)
        
    # src must exist as a dir
    try:
        src = os.path.realpath(src, strict=True)
    except:
        print("Source must exist, and can't a be link")
        sys.exit(-1)
    if not(os.path.isdir(src)): # link check done with real path, strict=True
        print("Source must be a directory")
        invInput(c)
        
    # given period should be int > 0
    try:
        p = int(p)
        if p <= 0:
            raise TypeError("Period is non-positive int")
    except:
        print("Supplied period should be a positive int")
        invInput(c)
        
    # if dest doesn't exist, it should be created
    destCreatedNow = False
    if os.path.isdir(dest):
        dest = os.path.realpath(dest)
        if os.path.islink(dest):
            print("Dest cannot be a link")
            invInput(c)
    else:
        try:
            os.makedirs(dest) # logged in main, relevant flag is below
            dest = os.path.realpath(dest)
            destCreatedNow = True
        except Exception as e:
            print(e)
            print("Replica dir doesn't exist and could not be created")
            sys.exit(-1)
            
    # log file not in dest/src, and dest/src not each other's parent:
    if src in logFileLocation or dest in logFileLocation:
        print("Log file cannot be located in the src or dest directories")
        sys.exit(-1)
    if dest in src or src in dest:
        print("Source directory cannot be inside destination, and vice versa")
        sys.exit(-1)
    
    return (src, dest, p, logF, destCreatedNow)

def pickNewName(currentName):
    '''Currently implemented to append a timestamp after a filename.
    NOTE: No validation made for the possible path length (LIMITATION!)
    '''
    return currentName + "_" + str(timestamp())

def getCurrentTime():
    '''Wrapper function:
    Returns datetime.datetime.now(); added for eventual time str formatting
    '''
    currentTime = dt.datetime.now()
    return currentTime

def endSyncCycle(cycleStart, syncPeriod):
    '''Ends the cycle and calculates the waiting time till next cycle start
    cycleStart - datetime object marking the sync cycle start
    syncPeriod - int, seconds between two sync cycle starts/ends
    Returns the waiting time in seconds untill next sync cycle start
    '''
    endTime = getCurrentTime()
    timeDelta = endTime - cycleStart
    # waitingTime = syncPeriod - (timeDelta.seconds % syncPeriod)
    return (syncPeriod - (timeDelta.seconds % syncPeriod))

def getDirSnapshotAndAdapt(dirsDict, curSrcDir, lvlFromSrc, 
                           topLevelAbsPath, mainDestAbsPath):
    '''Argument directory of type BaseDir/SrcDir
    '''
    logger.debug(f"Add '{curSrcDir.getRelPath()}' to snap lvl '{lvlFromSrc}'")
    if lvlFromSrc in dirsDict:
        dirsDict[lvlFromSrc].append(curSrcDir)
    else:
        dirsDict[lvlFromSrc] = [curSrcDir]
        
    curAbsPath = os.path.join(topLevelAbsPath, curSrcDir.getRelPath())
    curAbsPath = os.path.normpath(curAbsPath)
    logger.debug(f"Looking for dirs/files in '{curAbsPath}'")
    with os.scandir(curAbsPath) as dirEntries:
        for entry in dirEntries:
            foundPath = os.path.normpath(entry.path)
            if entry.is_file(follow_symlinks=False):
                foundFile = SrcFile(foundPath)
                lg1 = f"Found file  in '{curAbsPath}': "
                lg2 = f" '{foundFile.getName()}' added to src snapshot"
                logger.debug(lg1+lg2)
                curSrcDir.addFileToDir(foundFile)
            elif entry.is_dir(follow_symlinks=False):
                newSrcDir = SrcDir(foundPath, topLevelAbsPath)
                logger.debug(f"Src sub-dir found, '{newSrcDir.getName()}'")
                if curSrcDir.getNewRelPathInDest():
                    newSrcDir.setNewRelPathInDest(curSrcDir)
                    lg0 = "Parent dir set up for different name in dest. "
                    lg1 = "Therefore, this will be synced with different name "
                    lg2 = "in the dest because of inherited naming conflict; "
                    lg3 = f"original name: '{newSrcDir.getRelPath()}' "
                    lg4 = f"-> '{newSrcDir.getNewRelPathInDest()}'"
                    logger.error(lg0+lg1+lg2+lg3+lg4)
                    newD = (os.path.join(mainDestAbsPath, 
                                         newSrcDir.getNewRelPathInDest()))
                    try:
                        os.mkdir(newD)
                        logger.info(f"Created dir '{newD}'")
                    except Exception as e:
                        lg1 = f"Syncing of '{foundPath}' expected to fail "
                        lg2 = "because of unsolvable naming conflict"
                        logger.critical(lg1+lg2, exc_info=True)
                else:
                    newSrcDir.destEquivalenceCheckAndAdapt(mainDestAbsPath,
                                                           pickNewName)
                getDirSnapshotAndAdapt(dirsDict, newSrcDir, lvlFromSrc + 1, 
                                       topLevelAbsPath, mainDestAbsPath)
            else:
                lg1 = "Found object is neither a file (unless link), "
                lg2 = f"nor a dir: '{foundPath}' -> not added to snap!!!"
                logger.warning(lg1+lg2)

def fetchExistingDestFiles(dirAbsPath, existingFiles, existingDirs):
    '''Creates a dictionary, whose keys are hashed contents of files,
    and the values are tuples of (relativePath, fileOwner, owningUserGrp, \
                                  permission bits)
    '''
    logger.debug(f"Looking for dir/files in '{dirAbsPath}'")
    with os.scandir(dirAbsPath) as dirEntries:
        for entry in dirEntries:
            foundPath = os.path.normpath(entry.path)
            if entry.is_file(follow_symlinks=False):
                fileFound = DestFile(foundPath)
                logger.debug(f"File found, '{fileFound.getName()}'")
                logger.debug(f"   at '{foundPath}'")
                newKey = fileFound.getHash()
                if newKey not in existingFiles:
                    logger.debug("File is unique so far")
                    existingFiles[newKey] = []
                else:
                    logger.debug("File is a duplicate of already found one(s)")
                # logger.debug(f"Fild about to be added fro tracking: '{foundPath}'")
                # apparently the string from inside the tupples inside the
                # dict values get r'the path' at time of adding/retreiving?
                existingFiles[newKey].append((foundPath, fileFound))
                lg1 = "   File appended for tracking; "
                lg2 = f"updated list:\n     {existingFiles[newKey]}\n"
                logger.debug(lg1+lg2)
            elif entry.is_dir(follow_symlinks=False):
                logger.debug(f"Dir found, '{foundPath}', following it")
                existingDirs.append(foundPath)
                logger.debug(f"Dir appended for tracking:\n    {existingDirs}")
                fetchExistingDestFiles(foundPath, existingFiles,
                                       existingDirs)

def clearExistingDestFiles(dirAbsPath, existingFiles, existingDirs):
    '''Goes through a directory and it's children and stops tracking all
    paths (files and dirs) in existingFiles and existingDirs
    dirAbsPath, string - abs path to some tracked sub-dir in dest dir
    existingFiles, dict of {hashValue:list(tuples(fileAbsPath, File object))}
    existingDirs, list(destination dir relative paths)
    '''
    logger.debug(f"Chosing objects to stop tracking from '{dirAbsPath}'")
    with os.scandir(dirAbsPath) as dirEntries:
        for entry in dirEntries:
            foundPath = os.path.normpath(entry.path)
            if entry.is_file(follow_symlinks=False):
                logger.debug(f"File found at '{foundPath}'")
                fileFound = DestFile(foundPath)
                h = fileFound.getHash()
                toPop = []
                try:
                    for i in range(len(existingFiles[h])):
                        # lg1 = f"About to compare dirAbsPath={dirAbsPath} with "
                        # lg2 = f" path from file dict: {existingFiles[h][i]}\n"
                        # lg3 = f"{os.path.normpath(dirAbsPath)}    vs     "
                        # lg4 = f"{os.path.normpath(existingFiles[h][i][0])}"
                        # logger.debug(lg1+lg2+lg3+lg4)
                        logger.debug(f"Compare with {existingFiles[h][i]}")
                        if dirAbsPath in os.path.normpath(existingFiles[h][i][0]):
                            lg1 = "Picked for untracking: "
                            logger.debug(lg1 + f"'{existingFiles[h][i][0]}'")
                            toPop.append(i)
                    for i in toPop:
                        untracked = existingFiles[h].pop(i)[0]
                        logger.debug(f"Stopped tracking of '{untracked}'")
                        # logger.debug("Nothing cleared, probably cleared before")
                except Exception as e:
                    lg1 = "A file has been modified during syncing: "
                    logger.critical(lg1 + f"'{foundPath}'", exc_info=True)
            elif entry.is_dir(follow_symlinks=False):
                # if sub dir is found remove it from tracked and look inside
                lg1 = f"Dir found, stop tracking it and follow '{foundPath}'"
                logger.debug(lg1)
                existingDirs.remove(foundPath)
                clearExistingDestFiles(foundPath, existingFiles, existingDirs)


def timeString(timestamp):
    '''Wrapper function:
    timestamp - datetime object
    Returns a formatted string describing timestamp
    (Currently unused function)
    '''
    # currently no special formatting used, can be easily added
    timestamp = str(timestamp)    
    return timestamp