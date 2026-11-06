import copy
import datetime as dt
import json
import re

class InvalidState(ValueError):
    pass

def require(condition, message):
    if not condition:
        raise InvalidState(message)

def date_ok(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        return False
    try:
        dt.date.fromisoformat(value)
        return True
    except ValueError:
        return False

def minute(value):
    require(isinstance(value, str) and re.fullmatch(r'\d{2}:\d{2}', value), 'Invalid time')
    hour, m = map(int, value.split(':'))
    require(0 <= hour < 24 and 0 <= m < 60, 'Invalid time')
    return hour * 60 + m

def integer(value, lo, hi):
    return type(value) is int and lo <= value <= hi

def validate_state(raw):
    require(isinstance(raw, dict), 'State must be an object')
    require(len(json.dumps(raw, ensure_ascii=False).encode()) <= 1900000, 'State too large')
    state = copy.deepcopy(raw)
    require(set(state) <= {'tasks', 'entries', 'times', 'settings'}, 'Unknown top-level fields')
    tasks = state.get('tasks')
    require(isinstance(tasks, list) and len(tasks) <= 500, 'Maximum 500 tasks')
    ids = set()
    for task in tasks:
        require(isinstance(task, dict), 'Invalid task')
        task_id = task.get('id')
        require(isinstance(task_id, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,100}', task_id), 'Invalid task id')
        require(task_id not in {'__proto__', 'constructor', 'prototype'} and task_id not in ids, 'Duplicate or reserved task id')
        ids.add(task_id)
        require(isinstance(task.get('title'), str) and 0 < len(task['title'].strip()) <= 200, 'Invalid title')
        require(integer(task.get('order', 0), 0, 1000000), 'Invalid order')
        rule = task.get('schedule')
        if rule is not None:
            require(isinstance(rule, dict) and rule.get('type') in {'manual', 'daily', 'even', 'odd', 'custom'}, 'Invalid schedule')
            if rule['type'] == 'custom':
                require(integer(rule.get('on'), 1, 365) and integer(rule.get('off'), 1, 365) and date_ok(rule.get('anchor')), 'Invalid custom schedule')
    entries = state.get('entries')
    times = state.setdefault('times', {})
    require(isinstance(entries, dict) and isinstance(times, dict), 'Invalid entries or times')
    count = 0
    for task_id, dates in entries.items():
        require(task_id in ids and isinstance(dates, dict), 'Unknown task in entries')
        count += len(dates)
        for date, status in dates.items():
            require(date_ok(date) and status in ('planned', 'done'), 'Invalid entry')
    require(count <= 50000, 'Maximum 50000 dated entries')
    for task_id, dates in times.items():
        require(task_id in ids and isinstance(dates, dict), 'Unknown task in times')
        for date, block in dates.items():
            require(date_ok(date) and date in entries.get(task_id, {}) and isinstance(block, dict), 'Time requires entry')
            kind = block.get('type', 'fixed')
            require(kind in {'fixed', 'wake', 'sleep', 'after'}, 'Invalid block type')
            if kind == 'fixed':
                require(minute(block.get('start')) < minute(block.get('end')), 'Invalid fixed interval')
            else:
                require(integer(block.get('offset'), 0, 1440) and integer(block.get('duration'), 1, 1440), 'Invalid relative interval')
                if kind == 'after':
                    require(isinstance(block.get('taskId'), str) and len(block['taskId']) <= 100, 'Invalid dependency id')
                    # Missing sources are retained to display warnings in the UI.
                    visited = {task_id}
                    current = block
                    while current.get('type') == 'after':
                        source = current['taskId']
                        require(source not in visited, 'Circular dependency')
                        visited.add(source)
                        current = times.get(source, {}).get(date, {})
    settings = state.setdefault('settings', {'wake': '07:00', 'sleep': '23:00'})
    require(isinstance(settings, dict), 'Invalid settings')
    require(minute(settings.get('wake')) < minute(settings.get('sleep')), 'Sleep must follow wake')
    return state
