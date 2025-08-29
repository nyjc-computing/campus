#!/bin/bash
# Pull changes for another branch without affecting unstaged changes

if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <branch-name>"
    exit 1
fi

BRANCH="$1"

if ! git show-ref --verify --quiet "refs/heads/$BRANCH"; then
    echo "Branch '$BRANCH' does not exist."
    exit 2
fi

git stash
git checkout "$BRANCH" && git pull
git checkout deployment-refactor
git stash pop
