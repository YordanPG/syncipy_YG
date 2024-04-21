# -*- coding: utf-8 -*-

import logging
import os
from hashlib import sha256 as hashAlgo
from shutil import copyfile as shutil_copyfile

logger = logging.getLogger(f"main.{__name__}")

def userHasWritePermForDir(absPathName):
    ''' Not yet implemented...'''
    return True


class BaseFile(object):
    '''This class (under-)defines a file object. It is not aware where it is
    in a file system, so location must always be kept in mind. Typically, it
    would belong to a directory class (which is aware of its relative location
    only).
    
    During creation, the file name (again, not a full path, just the tail),
    the file mode, owning user and group, as well the file size are obtained.
    Those can be refreshed at a later time by specifying the file location.
    pathName, str, this is a path to the file described in this class
    '''
    
    def __init__(self, pathName):
        # pathName is an absolute path to a file
        directory, name = os.path.split(pathName)
        self.name = name # file name, not a path
        self.mode = 0 # mode/permission bits, int?
        self.uid = 0 # owning user id
        self.gid = 0 # owner group id
        self.size = 0 # size in bytes
        self.refreshAttributes(directory)
        self.hashHex = "" # only set for SrcFile and DestFile objects

    def refreshAttributes(self, fileLocationPath):
        """Refreshes the attributes of self (currently unused)
        fileLocationPath, str, an absolute path to the parent dir of self
        """
        updated = os.stat(os.path.join(fileLocationPath, self.name))
        self.mode = updated.st_mode
        self.uid = updated.st_uid
        self.gid = updated.st_gid
        self.size = updated.st_size

    def calculateHash(self, fileLocationPath):
        '''Calculates hash of file content using the imported hashlib algorithm
        Note: chosen algorithm should only do hashing based on byte stream
        fileLocationPath, str, an absolute path to the parent dir of self
        '''
        hashFunc = hashAlgo()
        logger.debug(f"About to hash '{self.name}' using {hashFunc.name}")
        f = os.path.join(fileLocationPath, self.name)
        with open(f, 'rb') as file:
            while True:
                chunk = file.read(hashFunc.block_size)
                if not chunk:
                    break
                hashFunc.update(chunk)
        return hashFunc.hexdigest()

    def getHash(self):
        '''Returns a str, the hash value of a file byte content, maybe empty.
        '''
        return self.hashHex

    def getName(self):
        '''Returns a str, the name of a file
        '''
        return self.name # string

    def getSize(self, unit = "byte"):
        '''Returns the size of a file, as an int or a float, dependng on the
        unit of size, which can be specified by the parameter 'unit'.
        Unit can be set to:
            'kibi', returning a float representing kilobytes
            'mebi', returning a float representing megabytes
            'gibi', returning a float representing gigabytes
            Anything else, returning an int representing a number of bytes
        '''
        if unit == "kibi":
            return self.size / 1024 # float
        elif unit == "mebi":
            return self.size / (1024 ** 2) # float
        elif unit == "gibi":
            return self.size / (1024 ** 3) # float
        else:
            return self.size # int

    def getModeAndOwnership(self):
        '''Return tuple of the file mode, owning user and group id
        '''
        return (self.mode, self.uid, self.gid) # tuple(int, int, int)


class SrcFile(BaseFile):
    '''Used to define a file residing in the source directory.
    '''
    
    def __init__(self, pathName):
        BaseFile.__init__(self, pathName)
        # self.absName = pathName
        self.hashHex = self.calculateHash(os.path.split(pathName)[0])

    def cpFile(self, curAbsP, newAbsP):
        '''Tries to copy the file from curAbsP(str) to newAbsP(str), both
        absolute paths
        Returns True on success
        '''
        try:
            shutil_copyfile(curAbsP, newAbsP)
            logger.info(f"File copied: '{curAbsP}' -> '{newAbsP}'")
            return True
        except Exception as e:
            logger.error(f"Could NOT copy: '{curAbsP}' -> '{newAbsP}'",
                         exc_info=True)
            return False

    def chmodChownFile(self, absPath):
        '''Tries to change the mode and ownership of a some file with path
        specified by absPath(str), so that they match those of the self file.
        '''            
        # current mode, userid, grpid, of the replicated file
        fileStat = os.stat(absPath)
        curMode = fileStat.st_mode
        curUserID = fileStat.st_uid
        curGrpID = fileStat.st_gid
        # new mode, userid, grpid of an original source file
        newMode, newUserID, newGrpID = self.getModeAndOwnership()
        
        lg1 = f"Looking into file {absPath}, mode={curMode}, "
        lg2 = f"owning user: {curUserID}, userGrp={curGrpID} for potential "
        lg3 = f"change to {newMode}, {newUserID}, {newGrpID}"
        logger.debug(lg1+lg2+lg3)
        # then chmod
        if curMode != newMode:
            try:
                os.chmod(absPath, newMode)
                logger.debug("  MODE changed")
            except Exception as e:
                logger.debug(f"  FAILED mode change, '{absPath}'",
                                exc_info=True)
        else:
            logger.debug("  No need for mode change")

        # then chown
        if (curUserID, curGrpID) != (newUserID, newGrpID):
            try:
                os.chown(absPath, newUserID, newGrpID)
                logger.debug("  OWNER changed")
            except Exception as e:
                logger.debug(f"  FAILED ownership change, '{absPath}'",
                                exc_info=True)
        else:
            logger.debug("No need for ownership change")

    def wrapCpChmodChown(self, currentAbsP, newAbsP):
        '''Combines copy, chmod and chown.
        currentAbsP, str, absolute path of file in source dir
        newAbsPath, str, target path (absolute) of file in replica
        '''
        if self.cpFile(currentAbsP, newAbsP):
            self.chmodChownFile(newAbsP)

    def syncFile(self, srcD, srcDirPath, destDirPath,
                 destFiles, destDirs,
                 stopTrackingExisting,
                 startTrackingExisting,
                 pickUniqName):
        '''Tries to sync a file in one of the following ways:
            - Same file already exists in main target dir, move accordingly.
            - Same file doesn't exist, so copy the file from source
            - (neccessary path is taken, try resolving the naming conflict)
        Arguments:
            srcD, SrcDir object, to which the file belongs
            srcDirPath, str, absolute path to the main source directory
            destDirPath, str, absolute path to the main destination directory
            destDirs, list of directories (absolute paths) which are under
                the main dest dir
            destFiles, dictionary, describing files found in the dest dir
            stopTrackingExisting, function from outside class, removes tracked
                files/dirs form the tracked ones. Should take a str, abs path
                to a directory being tracked (together with its contents);
                the existing files dict and the existing dirs list;
                Return value/type is irrelevant/unused
            startTrackingExisting, function from outside class, tracking
                the existing files dict and existing dirs list;
                should take as arguments: the changed abs path string,
                the existing files dict and the existing dirs list;
                Return value/type is irrelevant/unused
            pickUniqName, function from outside class, should accept str and
                returns same string with appended timestamp (as per current
                implementation). No validation for the path length is done!
        '''
        fRelP = os.path.join(srcD.getRelPath(), self.getName())
        
        curAbsP = os.path.join(srcDirPath, fRelP)
        curAbsP = os.path.normpath(curAbsP)
        
        newAbsP = os.path.join(destDirPath, fRelP)
        newAbsP = os.path.normpath(newAbsP)
        
        if not(os.path.exists(newAbsP)):
            logger.debug("Copying file, abs path is free")
            self.wrapCpChmodChown(curAbsP, newAbsP)
        # otherwise, something exists at dest path, handle such case
        else:
            logger.warning("Name conflict detected - absolute path not unique")
            # rename whatever is keeping hold of the absolute path
            # where the src file would be synced to, then sync, if possible
            # If not possible, the src file is going to be synced
            # in the same relative location, but under a different
            # file name, i.e. same name with appended time stamps
            newAbsP_uniq = pickUniqName(newAbsP) # not a class method
            mustChangeOriginalNameInDest = False
            # if that's a directory, ignoring links
            if os.path.isdir(newAbsP) and not(os.path.islink(newAbsP)):
                logger.warning(f"Name conflict with existing dir: '{newAbsP}'")
                # stop tracking files/dir from there, should get renamed
                destDirs.remove(newAbsP)
                stopTrackingExisting(newAbsP, destFiles, destDirs)
                try:
                    os.rename(newAbsP, newAbsP_uniq)
                    lg1 = "Existing destination directory renamed because of "
                    lg2 = f"naming conflict: '{newAbsP}' -> '{newAbsP_uniq}'"
                    logger.info(lg1 + lg2)
                    logger.debug("Start tracking files/dirs in new path")
                    destDirs.append(newAbsP_uniq)
                    startTrackingExisting(newAbsP_uniq, destFiles, destDirs) # not a class method
                    # if the new path is upstream of the current path
                    # (i.e. a file would need to move a level up, not down)
                    # with the renaming of the directory, the current abs path
                    # is now renamed as well, so update variable for such cases
                    if newAbsP in curAbsP:
                        lg1 = f"Deal with renaming consequence, '{curAbsP}' "
                        lg2 = "adapted to changed parent dir path name: "
                        lg3 = f"'{newAbsP_uniq}'"
                        logger.debug(lg1+lg3+lg3)
                        curAbsP = curAbsP.replace(newAbsP, newAbsP_uniq)
                except Exception as e:
                    logger.error("Existing dest dir could not be renamed ",
                                 exc_info=True)
                    # renaming failed, must restore tracked dirs/files
                    logger.debug("Again, tracking files/dirs from '{newAbsP}'")
                    destDirs.append(newAbsP)
                    startTrackingExisting(newAbsP, destFiles, destDirs)
                    mustChangeOriginalNameInDest = True
            # if it's file, must update it's entry in dict, ignoring links        
            elif os.path.isfile(newAbsP) and not(os.path.islink(newAbsP)):
                logger.warning(f"Name conflict with existing file: {newAbsP}")
                # stop tracking file
                fHash = BaseFile(newAbsP).calculateHash(os.path.split(newAbsP)[0])
                for t in destFiles[fHash]:
                    if newAbsP == t[0]:
                        logger.debug(f"Stop tracking it, pending renaming")
                        destFiles[fHash].remove(t)
                        break
                try:
                    os.rename(newAbsP, newAbsP_uniq)
                    replacement = DestFile(newAbsP_uniq)
                    # start tracking again after renaming
                    destFiles[replacement.getHash()].append((newAbsP_uniq,
                                                             replacement))
                    logger.debug(f"Renamed '{newAbsP}' -> '{newAbsP_uniq}'")
                except Exception as e:
                    logger.error("Renaming on destination side failed",
                                 exc_info=True)
                    # renaming failed, start tracking old name again
                    logger.debug(f"Re-start tracking the file")
                    restore = DestFile(newAbsP)
                    destFiles[restore.getHash()].append((newAbsP, restore))
                    mustChangeOriginalNameInDest = True
            # anything else, just rename it
            else:
                try:
                    os.rename(newAbsP, newAbsP_uniq)
                    logger.debug(f"Renamed '{newAbsP}' -> '{newAbsP_uniq}'")
                except Exception as e:
                    logger.error("Renaming on destination side failed!",
                                 exc_info=True)
                    mustChangeOriginalNameInDest = True
            # if nothing else worked, synced file gets new name
            if mustChangeOriginalNameInDest:
                lg1 = "Abs path conflict could not be resolved"
                lg2 = "Changing original file name when copying to dest"
                logger.error(lg1+lg2)
                self.wrapCpChmodChown(curAbsP, newAbsP_uniq)
            else:
                logger.debug("Abs path conflict resolved")
                self.wrapCpChmodChown(curAbsP, newAbsP)
                # self.wrapMvChmodChown(curAbsP, newAbsP, srcFile)


class DestFile(SrcFile):
    '''Used to define a file residing the replica directory
    '''
    
    def mvFile(self, currentAbsP, newAbsP):
        '''Assumes that there is no file/dir at the specified path.
        currentAbsP, str, the absolute path to file
        newAbsP, str, the absolute path that currentAbsP file needs to move to
        Returns True, if successful, False otherwise
        '''
        try:
            os.rename(currentAbsP, newAbsP)
            logger.info(f"MOVED file: '{currentAbsP}' -> '{newAbsP}'")
            return True
        except Exception as e:
            logger.error(f"FAILED move '{currentAbsP}' -> '{newAbsP}'",
                         exc_info=True)
            return False

    def chmodChownFile(self, absPath, srcFile):
        '''Tries to change the mode and ownership of a dest file, so that they
        match those of the source file
        absPath, str, the absolute path of the file described by self
        srcFile, SrcFile object, whose mode, owning user and group id are
        going to be applied to absPath(self)
        '''            
        # current mode, userid, grpid
        curMode, curUserID, curGrpID = self.getModeAndOwnership()
        # new mode, userid, grpid
        newMode, newUserID, newGrpID = srcFile.getModeAndOwnership()
        
        lg1 = f"Looking into file {absPath}, mode={curMode}, "
        lg2 = f"owning user: {curUserID}, userGrp={curGrpID} for potential "
        lg3 = f"change to {newMode}, {newUserID}, {newGrpID}"
        logger.debug(lg1+lg2+lg3)
        # then chmod
        if curMode != newMode:
            try:
                os.chmod(absPath, newMode)
                logger.debug("  MODE changed")
                self.mode = newMode
            except Exception as e:
                logger.debug(f"  FAILED mode change, '{absPath}'",
                                exc_info=True)
        else:
            logger.debug("  No need for mode change")

        # then chown
        if (curUserID, curGrpID) != (newUserID, newGrpID):
            try:
                os.chown(absPath, newUserID, newGrpID)
                logger.debug("  OWNERSHIP changed")
                self.uid = newUserID
                self.gid = newGrpID
            except Exception as e:
                logger.debug(f"  FAILED ownership change, '{absPath}'",
                                exc_info=True)
        else:
            logger.debug("  No need for ownership change")

    def wrapMvChmodChown(self, currentAbsP, newAbsP, srcFile):
        '''Combines move(rename), chmod and chown.
        currentAbsP, str, absolute path of file in source dir
        newAbsPath, str, target path (absolute) of file in replica
        srcFile, SrcFile object, whose mode, owning user and group id are
        going to be applied to absPath(self)
        '''
        logger.debug(f"Moving file '{currentAbsP}' -> '{newAbsP}'")
        if self.mvFile(currentAbsP, newAbsP):
            self.chmodChownFile(newAbsP, srcFile)
        else:
            self.chmodChownFile(currentAbsP, srcFile)

    def handleMatchingFileSync(self, curAbsP, newAbsP, srcFile,
                               destFiles, destDirs,
                               stopTrackingExisting,
                               startTrackingExisting,
                               pickUniqName):
        '''When an existing file in destination contains the same data as
        a file from source, this function attempts to move it and change
        mode and ownership, if such actions are neccessary, in order for this
        file to match the source file's relative location, mode and ownership.
        It would attempt to deal with naming conflicts.
        If these actions cannot go through and the naming collision persists,
        the file would be moved to the correct location, however the original
        source file name would be changed (time stamp appended).
        (analogous approached is used when a source file is copied under a
         different name within the same relative location)
        Arguments:
            curAbsP, str, current absolute path of existing file in dest,
                which matches a file in source
            newAbsP, str, the absololute path, to which the source file
                has to be synced to
            srcFile, SrcFile object, the file in src, matched by curAbsP
            destDirs, list of directories (absolute paths) which are under
                the main dest dir
            destFiles, dictionary, describing files found in the dest dir
            stopTrackingExisting, function from outside class, removes tracked
                files/dirs form the tracked ones. Should take a str, abs path
                to a directory being tracked (together with its contents);
                the existing files dict and the existing dirs list;
                Return value/type is irrelevant/unused
            startTrackingExisting, function from outside class, tracking
                the existing files dict and existing dirs list;
                should take as arguments: the changed abs path string,
                the existing files dict and the existing dirs list;
                Return value/type is irrelevant/unused
            pickUniqName, function from outside class, should accept str and
                returns same string with appended timestamp (as per current
                implementation). No validation for the path length is done!
        '''
        lg1 = f"Src file '{srcFile.getName()}' matches existing file in "
        lg2 = f"dest: '{curAbsP}'"
        logger.info(lg1+lg2)
        if curAbsP == newAbsP:
            logger.debug("No need to move, file already in its place")
            self.chmodChownFile(curAbsP, srcFile)
        # if file needs to move, and nothing exists at new path
        elif not(os.path.exists(newAbsP)):
            lg1 = "Moving file, abs path is free, "
            lg2 = f"'{curAbsP}' -> '{newAbsP}'"
            logger.debug(lg1+lg2)
            self.wrapMvChmodChown(curAbsP, newAbsP, srcFile)
        # otherwise, something exists at new path, handle such case
        else:
            # rename whatever is keeping hold of the absolute path
            # where the src file would be synced to, then sync, if possible
            # If not possible, the src file is going to be synced
            # in the same relative location, but under a different
            # file name, i.e. same name with appended time stamps
            newAbsP_uniq = pickUniqName(newAbsP)
            mustChangeOriginalNameInDest = False
            # if that's a directory, ignoring links
            if os.path.isdir(newAbsP) and not(os.path.islink(newAbsP)):
                logger.warning(f"Name conflict with existing dir: '{newAbsP}'")
                # clear tracked files/dir from there, should get renamed
                destDirs.remove(newAbsP)
                stopTrackingExisting(newAbsP, destFiles, destDirs)
                try:
                    os.rename(newAbsP, newAbsP_uniq)
                    lg1 = "Existing destination directory renamed because of "
                    lg2 = f"naming conflict: '{newAbsP}' -> '{newAbsP_uniq}'"
                    logger.debug(lg1 + lg2)
                    logger.debug("Start tracking files/dirs in new path")
                    destDirs.append(newAbsP_uniq)
                    startTrackingExisting(newAbsP_uniq, destFiles, destDirs)
                    # if the new path is upstream of the current path
                    # (i.e. a file would need to move a level up, not down)
                    # with the renaming of the directory, the current abs path
                    # is now renamed as well, so update variable for such cases
                    if newAbsP in curAbsP:
                        curAbsP = curAbsP.replace(newAbsP, newAbsP_uniq)
                except Exception as e:
                    lg1 = "Existing dest dir could not be renamed: "
                    lg2 = f"'{newAbsP}' -> '{newAbsP_uniq}'"
                    logger.error(lg1+lg2, exc_info=True)
                    lg1 = "Naming conflict unresolved, set up new name "
                    lg2 = "for file syncing instead"
                    logger.warning(lg1+lg2)
                    # directory renaming failed
                    # must restore existing sub dirs and files as they were
                    destDirs.append(newAbsP)
                    startTrackingExisting(newAbsP, destFiles, destDirs)
                    mustChangeOriginalNameInDest = True
            # if it's a file, must update its entry in dict, ignoring links        
            elif os.path.isfile(newAbsP) and not(os.path.islink(newAbsP)):
                # stop tracking file
                fHash = BaseFile(newAbsP).calculateHash(os.path.split(newAbsP)[0])
                for t in destFiles[fHash]:
                    if newAbsP == t[0]:
                        destFiles[fHash].remove(t)
                        break
                try:
                    os.rename(newAbsP, newAbsP_uniq)
                    replacement = DestFile(newAbsP_uniq)
                    destFiles[replacement.getHash()].append((newAbsP_uniq, replacement))
                    logger.debug(f"Renamed '{newAbsP}' -> '{newAbsP_uniq}'")
                except Exception as e:
                    lg1 = "Existing dest file could not be renamed; "
                    lg2 = "restoring snap of dest, but failure expected"
                    logger.error(lg1+lg2, exc_info=True)
                    # renaming failed, start tracking old name again
                    restore = DestFile(newAbsP)
                    # key must exist, if nothing changed since snapshot taken
                    destFiles[restore.getHash()].append((newAbsP, restore))
                    mustChangeOriginalNameInDest = True
            # anything else, just rename it
            else:
                try:
                    os.rename(newAbsP, newAbsP_uniq)
                    logger.debug(f"Renamed {newAbsP} -> {newAbsP_uniq}")
                except Exception as e:
                    logger.error("File naming conflict unresolved",
                                 exc_info=True)
                    mustChangeOriginalNameInDest = True
            # if nothing else worked, synced file gets new name
            if mustChangeOriginalNameInDest:
                lg1 = "Abs path conflict could not be resolved; "
                lg2 = "changing original file name in dest: "
                lg3 = f"'{newAbsP}' -> '{newAbsP_uniq}'"
                logger.error(lg1+lg2+lg3)
                self.wrapMvChmodChown(curAbsP, newAbsP_uniq, srcFile)
            else:
                logger.debug("   abs path conflict resolved")
                self.wrapMvChmodChown(curAbsP, newAbsP, srcFile)


class BaseDir(BaseFile):
    '''Defines a base directory class.
    Assumes the provided path is indeed a directory (should not be link)
    pathName, str, describing a path to e directory
    referencePath, str, describing a path, which points to a (grand-)parent
    directory of significance, i.e. the main src/replica directory.
    '''
    
    def __init__(self, pathName, referencePath):
        # self.size is going to always be 0
        BaseFile.__init__(self, pathName)
        # self.absPath = pathName
        self.relPath = os.path.relpath(pathName, referencePath)
        self.containedFiles = []
        # self.size = 0 # attribute meaning is changed

    def getRelPath(self):
        return self.relPath

    def getContainedFiles(self):
        return self.containedFiles

    def addFileToDir(self, baseFileObj):
        '''baseFileObj of type BaseFile (or child thereof), which is assigned
        as beloging to self, as a BaseDir object
        '''
        self.containedFiles.append(baseFileObj)
        # no need to refresh baseFileObj's attributes, because it is
        # immediately added to a baseDirObj, when it is found and created
        # baseFileObj.refreshAttributes(self.absPath)
        self.size += baseFileObj.getSize()

    def __str__(self, updated = False):
        '''Communicates the files with their sizes in bytes, as well as the
        total. Based on the information captured during a snapshot taking.
        '''
        res = "Content of '" + self.relPath + "':\n"
        for f in self.containedFiles:
            res += f"    {f.getName()} of size {f.getSize()}\n"
        res += "  Total size of these files is {self.getSize()} bytes."
        return res


class SrcDir(BaseDir):
    '''The subclass is meant to be used for directories under the the main
    source directory, which needs to be synced. It adds the possibility to 
    reuse equivalent directories, which exist in the destination directory,
    as well as to resolve potential naming conflicts when syncing src -> dest.
    
    Equivalent directory in the sense that it has the same relative path 
    from the main destinatin dir, as the to-be-synced directory has, 
    relative from the main source dir. In case it is a non-dir file,
        it is considered to be a potential naming conflict.
    
    Reusing such directory means to:
        - Copy new files there, from the source dir;
        - Rename (update) a file existing in it, if it is considered to be the 
            same as a file found in the source directory (to match paths);
        - Remove files from there, if those are not present in the source dir.
    
    Refer to the equivalence check function doc string for more information
    '''
    
    def __init__(self, pathName, referencePath):
            BaseDir.__init__(self, pathName, referencePath)
            self.hasDestEquivalent = False
            self.destEquivalentReusable = False
            self.newRelPathInDest = ''
            # self.destEquivalenceCheck() # only if it makes sense
    
    def destEquivalenceCheckAndAdapt(self, mainDestPath, pickUniqName):
        '''Check if the equivalen directory/file exists in the dest folder.
        mainDestPath, str, absolute path of the main replica directory
        pickUniqName, function from outside class, should accept str and
            returns same string with appended timestamp (as per current
            implementation). No validation for the path length is done!
        
        Side effect1 : if such directory exists, it is assumend that it can
            be written into, so it is going to be used for copying into it.
        Side effect 2: if such non-dir file exists, it is going to be
            renamed, if possible, otherwise the source dir will be copied
            under an altered name.
        '''
        logger.info(f"Check naming conflicts for '{self.getRelPath()}'")
        checkPath = os.path.join(mainDestPath, self.getRelPath()) # abs path
        checkPath = os.path.normpath(checkPath)
        # If the same relative dir exists in the mainDestDirectory
        if os.path.exists(checkPath):
            # if it's a dir, consider equivalent; care if it is a link?!
            if os.path.isdir(checkPath) and not(os.path.islink(checkPath)):
                lg1 = "Dir in dest exists, which has the same abs path "
                lg2 = f"needed for syncing: '{checkPath}'"
                logger.info(lg1+lg2)
                # LIMITATION: assuming that this directory can be written to
                self.hasDestEquivalent = True
                self.destEquivalentReusable = True
                logger.debug(f"Dir in dest assumed to be reusable")
            else:
                # whatever may be existing, try to rename it so that we can
                # create directory with the same relative path as in src
                # If not possible, dir synced under different name
                lg1 = "Non-dir file exists at path, attempt to resolve "
                lg2 = f"naming conflict at '{checkPath}'"
                logger.warning(lg1+lg2)
                try:
                    renameToPath = pickUniqName(checkPath)
                    os.rename(checkPath, renameToPath)
                    lg1 = "Non-dir file occupying the absolute path was "
                    lg2 = f"renamed '{checkPath}' -> '{renameToPath}'"
                    logger.warning(lg1+lg2)
                    os.mkdir(checkPath)
                    lg1 = "After name conflict resolution, re-created "
                    lg2 = f"path for dir in dest: '{checkPath}'"
                    logger.info(lg1+lg2)
                    self.hasDestEquivalent = True
                    self.destEquivalentReusable = True
                except Exception as e:
                    logger.error("File renaming failed", exc_info=True)
                    self.setNewRelPathInDest(pickUniqName)
                    lg0 = "Existing file/dir could not be renamed, "
                    lg1 = "src path set up to be backed up under new "
                    lg2 = f"name in dest, '{self.getRelPath()}' "
                    lg3 = f"-> '{self.getNewRelPathInDest()}'"
                    logger.warning(lg0+lg1+lg2+lg3)
                    newDir = os.path.join(mainDestPath, self.newRelPathInDest)
                    newDir = os.path.normpath(newDir)
                    os.mkdir(newDir)
                    logger.info("Therefore, created new dir: '{newDir}'")
        # if abs path is free
        else:
            # simply create it
            os.mkdir(checkPath)
            logger.info(f"Created new dir in dest: '{checkPath}'")
            self.hasDestEquivalent = True
            self.destEquivalentReusable = True
    
    def getNewRelPathInDest(self):
        return self.newRelPathInDest
    
    def setNewRelPathInDest(self, pickUniqName, directParentSrcDirObj = None):
        '''Used to set the name of a directory, which will be used for
        the back up, in the case that the original name cannot be used.
        
        pickUniqName, function from outside class, should accept str and
            returns same string with appended timestamp (as per current
            implementation). No validation for the path length is done!
        directParentSrcDirObj (optinal), SrcDir object, the parent dir of self
        It's assumed that if the optional argument is specified, it is the
            direct parent directory of self. Used in the case when
            there already was a dir name change upstream from self, so the
            name change is already known.
        '''
        if directParentSrcDirObj:
            directParentRelPath = directParentSrcDirObj.getNewRelPathInDest()
            # if the parent directory name is changed, only change that
            # one, but leave the dir name in question as is
            self.newRelPathInDest = os.path.join(directParentRelPath,
                                                 self.name)
        else:
            self.newRelPathInDest = pickUniqName(self.relPath)
        self.newRelPathInDest = os.path.normpath(self.newRelPathInDest)
