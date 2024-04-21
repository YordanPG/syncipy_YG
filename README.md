This is a Python script with the goal of periodically synchronizing two directories in
one direction only: from the source directory to the destination (replica) directory.

The main goal is having an exact replica of the source directory in the destination directory.
Additinaly, the script attempts to minimize delete and copy operations for already synced
and unchanged files, i.e. if a file content from source matches a file in the replica folder,
this would be handled in one of a few ways:
* No action required, if the destination file path, relative to the main destination directry,
  matches the source file path, relative to the main source directory;
* If those paths are not matching, the file in the destination would be moved, so that
  it matches the relative path of the source file;
* Any naming conflicts related to that are resolved, if possible:
  * Ideally, paths in destination, which are needed for source file/dir syncing, but are
    taken by other files/dirs in destination, are renamed;
  * If this is not possible, the source file/directory is still synced, but the name
  in destination is changed (currently by appending a time stamp to that path)

LIMITATIONS:
* No permission checks are done. The script assumes that the user has the neccessary
  permissions set. If this condition is not met, any number of failures can be
  expected;
* No attempt is made to resolve/synchronize links, those are currently ignored;
* On renaming of files/directories, in order to resolve name collisions, no validation
  is done for the length of the new path;
* So far only tested on Windows 10 with Python 3.11.7

The script follows these steps:
1. Validates user input.
3. Marks the start of synchronization.
4. Takes a snapshot of the source dir; as this is being done,
    adapts the destination directry structure as a prep for syncing.
    * NOTE: If for some reason, a src sub-dir cannot be synced into the
    respective dest location, sync will be attempted under a different
    name in dest, i.e.:
    ./src/subDir1 cannot be synced under ./dest/subDir1
    resolution: if possible, synced under /dest/subDir1_\<timestamp>
    * NOTE: the same applies for file name conflicts
5. Takes a snapshot of the dest dir (in its modified adapted state,
    see previous point)
6. Does the actual syncing by:
    - moving: if src file exists in dest, then that dest file is moved
        accordingly (if naming conflicts cannot be resolved, backed-up
        file would have different relative path in dest)
    - copy: if src file doesn't exist in dest, it is copied (possibly
        under new name, if naming conflicts could not be resolved)
7. After the syncing, removes obsolete files in dest
8. Removes obsolete directories in dest
9. Waits for the next cycle start, then repeats all the above.
    NOTE: Cycle is taken litterally, i.e.: if a sync period is set
    to 100 seconds and all the above steps have taken 110 seconds,
    then the next cycle would start in 90 s. If those took 280s,
    then the next cycle would start in 20 s. Aim is to have a cycle
    start at every n*100th second, for the sake of predictability and
    regularity.
