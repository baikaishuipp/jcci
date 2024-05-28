# -*- coding: UTF-8 -*-
import os

# sqlite3 path
db_path = os.path.dirname(os.path.abspath(__file__))
# git project clone file path
project_path = os.path.dirname(os.path.abspath(__file__))
# ignore file pattern
ignore_file = ['*/pom.xml', '*/test/*', '*.sh', '*.md', '*/checkstyle.xml', '*.yml', '.git/*']
# project package startswith
package_prefix = ['com.', 'cn.', 'net.']
# Whether to reparse the class when there is class data in the database
reparse_class = True
