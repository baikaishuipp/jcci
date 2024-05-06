# -*- coding: UTF-8 -*-
import os

db_path = os.path.dirname(os.path.abspath(__file__))
project_path = os.path.dirname(os.path.abspath(__file__))
ignore_file = ['*/pom.xml', '*/test/*', '*.sh', '*.md', '*/checkstyle.xml', '*.yml', '.git/*']
package_prefix = ['com.', 'cn.', 'net.']
