import os
import queue
import subprocess
import threading


class Backupper:

    def __init__(self):
        self.file_queue = queue.Queue()
        self.error_queue = queue.Queue()

    def backup(self, backup_file):
        """Backup paths described in the given file

        :param backup_file: file that describes what to backup
        :return:
        """
        print('\nLoading files to backup...')
        (backup_to, backup_from) = self.read_backup_info(backup_file)

        if not (backup_to, backup_from) == ('', ''):
            print('Scanning file system...\n')
            amount_to_back_up, items_to_backup = self.scan(backup_to, backup_from)
            if amount_to_back_up == 0:
                print("\n\nEverything's up to date!\n\n")
            else:
                print('Amount to backup: %s\n' % self.get_proper_size_from(amount_to_back_up))
                choice = input('Do you want to backup now? (y/n) ')
                if choice.lower() == 'y':
                    self.backup_with_threading(items_to_backup)

        input('---Press ENTER to exit---')

    def read_backup_info(self, backup_file):
        """Read file with given format

        :param backup_file: file that contains backup information
        :return: a string where to backup to and a list of strings from where to copy
        """
        try:
            file = open(backup_file, 'r')
        except FileNotFoundError as e:
            print("Couldn't open backup file:\n%s" % e)
            return '', ''

        file.readline()
        backup_to = file.readline().strip()

        file.readline()
        backup_from = []
        for line in file:
            backup_from.append(line.strip())

        file.close()

        return backup_to, backup_from

    def get_dest_path(self, backup_to, backup_from, start_of_base):
        """Create destination path

        :param backup_to: path of folder to backup to
        :param backup_from: path of folder/file to copy
        :param start_of_base: starting index of base folder
        :return: destination path
        """
        return backup_to + '\\' + backup_from[start_of_base:]

    def get_modified_paths(self, to_path, from_path, items, start_of_base):
        """Creates a list of paths that have been modified
        compared to the files/folders in the destination we want to backup to

        :param to_path:
        :param from_path: path of folder we want to copy the items from
        :param items: the files/folders we want to copy
        :param start_of_base: starting index of base folder
        :return: list of modified paths
        """
        modified_paths = []

        for item in items:

            new_path = os.path.join(from_path, item)
            dest_path = self.get_dest_path(to_path, new_path, start_of_base)

            src_mod_time = os.path.getmtime(new_path)
            if not os.path.exists(dest_path) or os.path.isdir(new_path):
                dest_mod_time = 0.0
            else:
                dest_mod_time = os.path.getmtime(dest_path)

            if src_mod_time > dest_mod_time:
                modified_paths.append(new_path)

        return modified_paths

    def scan(self, backup_to, backup_from):
        """Scans the backup_from paths for changes
        compared to the files/folders in backup_to path

        :param backup_to: path to folder where we want to backup files
        :param backup_from: paths to files/folders we want to backup
        :return: amount to backup in bytes, tuples of source and destination of files to backup
        """
        scan_list = []
        items_to_backup = []
        amount_to_back_up = 0

        for path in backup_from:
            start_of_base = path.find(os.path.basename(path))  # from where the folder name starts

            # insert one of the root folders to back up
            scan_list.insert(0, path)

            # while there is something to back up
            while len(scan_list) != 0:
                # here there are only directories in scan_list
                from_path = scan_list[0]
                del scan_list[0]
                try:
                    items = os.listdir(from_path)
                except PermissionError as e:
                    print('Permission error: %s' % e)
                    continue

                # get all items that have been modified
                paths_to_copy = self.get_modified_paths(backup_to, from_path, items, start_of_base)

                # if and item is a directory add it to the list of directories to check
                # if its a file than check how big it is and it to items to backup
                for p in paths_to_copy:
                    dest = self.get_dest_path(backup_to, p, start_of_base)
                    if os.path.isdir(p):
                        scan_list.insert(0, p)
                    else:
                        items_to_backup.insert(0, (p, dest))
                        amount_to_back_up += os.path.getsize(p)

        return amount_to_back_up, items_to_backup

    def copy(self, item):
        """Faster way to copy with error handling

        :param item: sources and destination tuple of a single file
        :return: error message if there was any
        """
        try:
            print('copying... ' + item[0])
            cmd = 'echo f | xcopy /q /h /y "%s" "%s"' % (item[0], item[1])
            success = subprocess.call(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
            if success != 0:
                print('-- ERROR! There was a problem copying: %s' % item[0])
                return 'There was a problem copying: %s' % item[0]
        except IOError as e:
            print("Couldn't copy: %s" % e)
            return e
        return ''

    def thread_copy_next(self):
        """Copy next item in file_queue with a thread

        :return:
        """
        while True:
            item = self.file_queue.get()
            if item is None:
                break
            error = self.copy(item)
            if error != '':
                self.error_queue.put(error)
            self.file_queue.task_done()

    def backup_with_threading(self, items_to_backup):
        """Copy given list of items with multiple threads

        :param items_to_backup: tuples of source and destination of files
        :return:
        """
        # create threads
        number_of_threads = 4
        threads = []
        for i in range(number_of_threads):
            t = threading.Thread(target=self.thread_copy_next)
            t.daemon = True
            t.start()
            threads.append(t)

        # fill up queue and wait for processing
        for item in items_to_backup:
            self.file_queue.put(item)
        self.file_queue.join()

        # stop threads
        for i in range(number_of_threads):
            self.file_queue.put(None)
        for t in threads:
            t.join()

        print("\n\nEverything's up to date!\n\n")

        # print errors that occurred during backup
        error_list = list(self.error_queue.queue)
        for e in error_list:
            print("Couldn't copy: %s" % e)

    def get_proper_size_from(self, amount):
        """Creates proper size format from amount

        :param amount: size in bytes
        :return: properly formatted size
        """
        size_names = ['B', 'KB', 'MB', 'GB', 'TB']
        name_idx = 0
        while amount > 1024:
            amount = float(amount) / 1024
            name_idx += 1
        amount = str(round(amount, 2))
        if '.' in amount:
            amount.rstrip('0').rstrip('.')
        return amount + ' ' + size_names[name_idx]


def main():
    b = Backupper()
    b.backup('backup_info.txt')


if __name__ == "__main__":
    main()
