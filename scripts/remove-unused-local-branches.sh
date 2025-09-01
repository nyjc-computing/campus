#!/bin/bash
# Remove local branches that do not track a remote branch

echo "WARNING: This will remove all local branches that do not track a remote branch."
echo

branches_to_delete=$(git branch --format='%(refname:short)' | while read branch; do
    if [ "$branch" != "main" ] && [ "$branch" != "master" ]; then
        upstream=$(git for-each-ref --format='%(upstream:short)' refs/heads/"$branch")
        if [ -z "$upstream" ]; then
            echo "$branch"
        fi
    fi
done)

if [ -z "$branches_to_delete" ]; then
    echo "No unused local branches to remove."
    exit 0
fi

echo "The following local branches will be deleted:"
echo "$branches_to_delete"
echo
read -p "Are you sure you want to delete these branches? [y/N]: " confirm
if [[ "$confirm" =~ ^[Yy]$ ]]; then
    for branch in $branches_to_delete; do
        git branch -D "$branch"
    done
    echo "Unused local branches removed."
else
    echo "Aborted. No branches were deleted."
fi
