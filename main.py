import meetup

GROUPS = [
    "Wilmington-DE-Web-Dev-Meetup",
    "Open-Data-Delaware",
]


def main():
    group = meetup.Group(GROUPS[0])
    members = group.members

    for m in members:
        print(m['name'])

if __name__ == '__main__':
    main()