
# -*- coding: utf-8 -*-

import logging
import time
import os
import sys

from helpingFuncs import printHelp, validateInput
from helpingFuncs import pickNewName, getCurrentTime, endSyncCycle 
from helpingFuncs import getDirSnapshotAndAdapt
from helpingFuncs import fetchExistingDestFiles, clearExistingDestFiles
from helpingClasses import SrcDir

def setUpLogging(logFile):
    '''Set up for logging go console and to a log file specified as arg.
    Returns a Logger object
    (for reference, see logger cookbook)
    '''
    # create logger and set default log lvl
    logger = logging.getLogger("main")
    logger.setLevel(logging.DEBUG)
    # create file handler which logs debug messages
    fh = logging.FileHandler(logFile, 'w')
    # fh.setLevel(logging.DEBUG)
    # create console handler with a higher log level
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    # create formatter and add it to the handlers
    formatter = logging.Formatter("%(asctime)s  %(name)s.%(levelname)s: %(message)s")
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)
    # add the handlers to the logger
    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


def main():
    '''Wraps up the whole syncing process:
        1. Does some check for user input, see validateInput func;
        2. Starts logging.
        3. Marks the start of syncing.
        4. Takes a snapshot of the source dir; as this is being done,
            adapts the destination directry structure a prep for syncing.
            NOTE: If for some reason, a src sub-dir cannot be synced into the
            respective dest location, sync will be attempted under a different
            name in dest, i.e.:
            ./src/subDir1 cannot be synced under ./dest/subDir1
            resolution: if possible, synced under /dest/subDir1_<timestamp>
            (ref to pickNewName func)
            NOTE: the same applies for file name conflicts
        5. Takes a snapshot of the dest dir (in its modified state,
            see previous point)
        6. Does the actual syncing by:
            - moving: if src file exists in dest, then that dest file is moved
                accordingly (if naming conflicts cannot be resolved, backed-up
                             file would have different relative path in dest)
            - copy: if src file doesn't exist in dest, it is copied (possibly
                under new name, if naming conflicts could not be resolved)
            (ref to pickNewName func)
        7. After the syncing, removes obsolete files in dest
        8. Removes obsolete directories in dest
        9. Waits for the next cycle start, then repeats all the above.
            NOTE: Cycle is taken litterally, i.e.: if a sync period is set
            to 100 seconds and all the above steps have taken 110 seconds,
            then the next cycle would start in 90 s. If those took 280s,
            then the next cycle would start in 20 s. Aim is to have a cycle
            start at every n*100th second, for the sake of predictability and
            regularity.
    '''
    # deal with user input
    cmdArgs = sys.argv
    # print("argv:", cmdArgs)
    # print()
    if "-h" in cmdArgs or "--help" in cmdArgs:
        printHelp()
        sys.exit(0)
    srcDirPath, destDirPath, syncPeriod, logFile, destCreatedNow = \
        validateInput(sys.argv)
    
    # input validated, start logging
    logger = setUpLogging(logFile)
    if destCreatedNow:
        msg = "Dest was not existing, but created during input validation"
        logger.info(msg)
    # log intial info: user, cmd arguments
    logger.info(f"  Source directory to be synced: '{srcDirPath}'")
    logger.info(f"  Destination directory for the sync: '{destDirPath}'")
    logger.info(f"  Log file: '{logFile}'")

    # syncing begings with  src dir snapshot + adapting dest dir structure
    while True:
        logger.info("Starting new sync cycle")
        currentCycleStart = getCurrentTime()
        logger.info("Getting snapshot of the source dir and adapting dest dir")
        srcSnap = dict()
        srcDir = SrcDir(srcDirPath, srcDirPath)
        getDirSnapshotAndAdapt(srcSnap, srcDir, 0,
                               srcDirPath, destDirPath)
        # # printing content of directories to be synced    
        # for depth in range(0, max(srcSnap.keys()) + 1):
        #     for d in srcSnap[depth]:
        #         print(d)

        # next phase: snapshot of dest dir after adapting, so it's up-to-date
        logger.info("Getting snapshot of the adapted state of dest dir")
        existingDestFiles = {}
        existingDestDirs = []
        fetchExistingDestFiles(destDirPath, existingDestFiles,
                               existingDestDirs)
        logger.debug("Existing file fetching done:")
        fetched = ""
        for l in existingDestFiles.values():
            for t in l:
                fAbsP = t[0]
                f = t[-1]
                fetched += f"  File path: {fAbsP}, hash value: {f.getHash()}\n"
        logger.debug(fetched)
        logger.debug(f"Existing dirs fetched: {existingDestDirs}")
        
        # Start the actual synchronisation
        logger.info("The actual syncing is now beginning")
        for lvl in srcSnap:
            for srcD in srcSnap[lvl]:
                # by now this sub-dir from src should have equivalent in dest
                # (even if it is going to have a new name in dest);
                # remove such equivalent dir from existingDestDirs list,
                # because later those are assumed to be empty and get deleted
                if lvl != 0: # man src/dest are not in the list
                    if srcD.getNewRelPathInDest(): # this just added
                        dirAbsP = os.path.join(destDirPath,
                                               srcD.getNewRelPathInDest())
                    else:
                        dirAbsP = os.path.join(destDirPath, srcD.getRelPath())
                    dirAbsP = os.path.normpath(dirAbsP)
                    logger.debug(f"Removing for existing dirs list: {dirAbsP}")
                    existingDestDirs.remove(dirAbsP)
                # now look into files of the src sub-dir
                for srcF in srcD.getContainedFiles():
                    h = srcF.getHash()
                    # if there is at least one file in dest with the same
                    # hash value, assume it is the same file and try to
                    # move/rename/leave as is
                    # in the case multiple such file exist in dest, try to
                    # chose the most suitable one, judging by paths
                    if h in existingDestFiles:
                        lg1 = "File from source already existing in dest, "
                        lg2 = "updating accordingly by moving/renaming..."
                        logger.debug(lg1+lg2)
                        fAbsPath_new = os.path.join(destDirPath,
                                                    srcD.getRelPath(),
                                                    srcF.getName())
                        fAbsPath_new = os.path.normpath(fAbsPath_new)
                        # take the first duplicate file, in case it's only one
                        fAbsPath, destF = existingDestFiles[h][0]
                        # and try to chose a better one
                        for t in existingDestFiles[h]:
                            trackedFilePath = t[0]
                            # pick existing file with potentially same path
                            if trackedFilePath == fAbsPath_new:
                                fAbsPath, destF = t
                                break
                            # file may have moved in a sub dir since last sync
                            elif len(trackedFilePath) > len(fAbsPath_new) \
                                    and fAbsPath_new in trackedFilePath:
                                fAbsPath, destF = t
                                break
                            # file may have moved in a parent dir since last sync
                            elif len(trackedFilePath) < len(fAbsPath_new) \
                                    and trackedFilePath in fAbsPath_new:
                                fAbsPath, destF = t
                                break
                        # such file needs to be moved to the corresponding location
                        # (possible naming conflicts to be dealt with)
                        # file mode and ownership should be changed accordingly
                        destF.handleMatchingFileSync(fAbsPath,
                                                     fAbsPath_new,
                                                     srcF,
                                                     existingDestFiles,
                                                     existingDestDirs,
                                                     clearExistingDestFiles,
                                                     fetchExistingDestFiles,
                                                     pickUniqName=pickNewName)
                        # what ever the outcome, file handled at best
                        # remove from dict, otherwise it'll be deleted later
                        duplicateFileNum = len(existingDestFiles[h])
                        if duplicateFileNum == 1:
                            existingDestFiles.pop(h)
                        else:
                            for i in range(duplicateFileNum):
                                if existingDestFiles[h][i][0] == fAbsPath:
                                    existingDestFiles[h].pop(i)
                                    break
                    else:
                        # hash value of src file not found in dest
                        srcF.syncFile(srcD, srcDirPath, destDirPath,
                                      existingDestFiles, existingDestDirs,
                                      clearExistingDestFiles,
                                      fetchExistingDestFiles,
                                      pickUniqName = pickNewName)
                        
        logger.info("Source files considered synced, see log file for details")
        
        logger.info("Removaing obsolete destination files")
        # removing all the files left in the existing dest files dict
        for l in existingDestFiles.values():
            for t in l:
                fAbsP = t[0]
                logger.debug(f" Going to delete file now: '{fAbsP}'")
                try:
                    os.remove(fAbsP)
                    logger.info(f"  File removed from destination, '{fAbsP}'")
                except Exception as e:
                    logger.error(f"  File cannot be removed: '{fAbsP}'",
                                 exc_info=True)
                
        logger.info("Removing obsolete destination directories")
        # dirs must be empty, so sort in such way, as to start from the
        # sub-most. As a back up, naively assume that large length implies
        # more sub-levels
        # using lambda for the sorting key. '\\' seems to apply in windows...
        if len(existingDestDirs) > 1:
            logger.debug("Reverse sorting dest dirs to be deleted")
            logger.debug(f"Directories meant for deletion:\n'{existingDestDirs}'")
            logger.debug("First, reversed sort by len of the dest dirs")
            try:
                existingDestDirs.sort(key=(lambda b: b.count("\\")),
                                      reverse=True)
                logger.info("Successfully sorted as intended")
            except Exception as e:
                logger.error("Unable to sort dirs as intended", exc_info=True)
                logger.debug(f"Dirs after sorting:\n'{existingDestDirs}'")
                existingDestDirs.sort(key=len, reverse=True)
        logger.info("Starting the actual deletion of obsolite directories")
        for d in existingDestDirs[:]:
            try:
                os.rmdir(d)
                logger.info(f"Dir removed from dest: '{d}'")
                existingDestDirs.remove(d)
            except Exception as e:
                logger.error(f"Dir cannot be removed: '{d}' ", exc_info=True)

        #clear snapshot variables before ending the cycle
        del srcSnap
        del existingDestFiles
        del existingDestDirs
        logger.info("Sync cycle finished")
        waitingTime = endSyncCycle(currentCycleStart, syncPeriod)
        msg = f"Next sync cycle starts in {waitingTime} seconds\n\n\n"
        logger.warning(msg)
        time.sleep(waitingTime)

if __name__ == "__main__":
    main()

