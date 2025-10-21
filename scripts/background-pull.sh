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

# Remember the current branch
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)

git stash
git checkout "$BRANCH" && git pull
git checkout "$CURRENT_BRANCH"
git stash pop
