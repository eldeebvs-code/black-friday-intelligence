"""Robots matching with wildcard/end anchors and longest-rule precedence."""
import re
from urllib.parse import urlsplit, unquote


class Robots:
    def __init__(self, text):
        self.groups = []
        agents, rules = [], []
        for line in text.splitlines() + ['User-agent: __end__']:
            line = line.split('#', 1)[0].strip()
            if ':' not in line:
                continue
            key, value = (s.strip() for s in line.split(':', 1))
            key = key.lower()
            if key == 'user-agent':
                if rules:
                    self.groups.append((agents, rules))
                    agents, rules = [], []
                agents.append(value.lower())
            elif key in ('allow', 'disallow') and agents and value:
                rules.append((key == 'allow', value))

    def can_fetch(self, agent, url):
        token = agent.split('/', 1)[0].lower()
        matches = [(max((len(a) if a != '*' else 0) for a in agents
                         if a == '*' or a in token), rules)
                   for agents, rules in self.groups if any(a == '*' or a in token for a in agents)]
        if not matches:
            return True
        level = max(n for n, _ in matches)
        split = urlsplit(url)
        path = unquote(split.path + ('?' + split.query if split.query else ''))
        decisions = []
        for n, rules in matches:
            if n != level:
                continue
            for allow, pattern in rules:
                pattern = unquote(pattern)
                end = pattern.endswith('$')
                raw = pattern[:-1] if end else pattern
                regex = '^' + '.*'.join(re.escape(p) for p in raw.split('*')) + ('$' if end else '')
                if re.search(regex, path):
                    decisions.append((len(raw.replace('*', '')), allow))
        return max(decisions)[1] if decisions else True
