
create_tables = '''
CREATE TABLE project (
	project_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
	project_name TEXT NOT NULL,
    git_url TEXT NOT NULL,
    branch TEXT NOT NULL,
    commit_or_branch_new TEXT NOT NULL,
    commit_or_branch_old TEXT,
    create_at TIMESTAMP NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE class (
	class_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
	filepath TEXT,
	access_modifier TEXT,
	class_type TEXT NOT NULL,
	class_name TEXT NOT NULL,
	package_name TEXT NOT NULL,
	extends_class TEXT,
	project_id INTEGER NOT NULL,
	implements TEXT,
	annotations TEXT,
	documentation TEXT,
	is_controller REAL,
	controller_base_url TEXT,
	commit_or_branch TEXT,
	create_at TIMESTAMP NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE import (
	import_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
	class_id INTEGER NOT NULL,
	project_id INTEGER NOT NULL,
	start_line INTEGER,
	end_line INTEGER,
	import_path TEXT,
	is_static REAL,
	is_wildcard REAL,
    create_at TIMESTAMP NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE field (
	field_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
	class_id INTEGER,
	project_id INTEGER NOT NULL,
	annotations TEXT,
	access_modifier TEXT,
	field_type TEXT,
	field_name TEXT,
	is_static REAL,
	start_line INTEGER,
	end_line INTEGER,
	documentation TEXT,
    create_at TIMESTAMP NOT NULL DEFAULT (datetime('now','localtime'))
);


CREATE TABLE methods (
	method_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
	class_id INTEGER NOT NULL,
	project_id INTEGER NOT NULL,
	annotations TEXT,
	access_modifier TEXT,
	return_type TEXT,
	method_name TEXT NOT NULL,
	parameters TEXT,
	body TEXT,
	method_invocation_map TEXT,
	is_static REAL,
	is_abstract REAL,
	is_api REAL,
	api_path TEXT,
	start_line INTEGER NOT NULL,
	end_line INTEGER NOT NULL,
	documentation TEXT,
    create_at TIMESTAMP NOT NULL DEFAULT (datetime('now','localtime'))
);
'''

