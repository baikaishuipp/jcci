
ENTITY = 'entity'
RETURN_TYPE = 'return_type'
PARAMETERS = 'parameters'
BODY = 'body'
METHODS = 'methods'
FIELDS = 'fields'

PARAMETER_TYPE_METHOD_INVOCATION_UNKNOWN = 'unknown'
#

#
NODE_TYPE_CLASS = 'class'
NODE_TYPE_METHOD = 'method'
NODE_TYPE_FIELD = 'field'
NODE_TYPE_MAPPER = 'mapper'
NODE_TYPE_MAPPER_SQL = 'sql'
NODE_TYPE_MAPPER_RESULT_MAP = 'resultMap'
NODE_TYPE_MAPPER_STATEMENT = 'statement'

DIFF_TYPE_CHANGED = 'changed'
DIFF_TYPE_IMPACTED = 'impacted'

JAVA_BASIC_TYPE = ['string', 'int', 'boolean', 'long', 'byte', 'short', 'float', 'double', 'char']
JAVA_UTIL_TYPE = [
    'ArrayList', 'Base64', 'Calendar', 'Collection', 'Collections', 'Comparators', 'Date', 'Dictionary',
    'EnumMap', 'EnumSet', 'EventListener', 'EventObject', 'Formatter',
    'HashMap', 'HashSet', 'Hashtable', 'Iterator', 'LinkedHashMap', 'LinkedHashSet', 'LinkedList',
    'List', 'ListIterator', 'Locale', 'Map', 'NavigableMap', 'NavigableSet', 'Objects',
    'Optional', 'OptionalDouble', 'OptionalInt', 'OptionalLong', 'Properties', 'Queue', 'Random',
    'RegularEnumSet', 'ResourceBundle', 'Scanner', 'ServiceLoader', 'Set', 'SimpleTimeZone',
    'SortedMap', 'SortedSet', 'Spliterator', 'Spliterators', 'SplittableRandom', 'Stack', 'StringJoiner',
    'StringTokenizer', 'TaskQueue', 'Timer', 'TimerTask', 'TimerThread', 'TimeZone', 'TimSort', 'TreeMap',
    'TreeSet', 'Tripwire', 'UUID', 'Vector', 'WeakHashMap']
MAPPING_LIST = ['PostMapping', 'GetMapping', 'DeleteMapping', 'PutMapping', 'PatchMapping', 'RequestMapping']
