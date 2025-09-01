#!/bin/bash
# Remove local branches whose upstream remote branch no longer exists (stale tracking branches)

echo "WARNING: This will remove all local branches whose upstream remote branch no longer exists (stale tracking branches)."
echo

# Prune remote-tracking branches first (like 'git remote prune origin')
git fetch --prune

branches_to_delete=$(git for-each-ref --format='%(refname:short) %(upstream:short)' refs/heads | while read branch upstream; do
    if [ "$branch" != "main" ] && [ "$branch" != "master" ] && [ -n "$upstream" ]; then
        # Check if the upstream branch exists
        if ! git show-ref --verify --quiet refs/remotes/$upstream; then
            echo "$branch"
        fi
    fi
done)

if [ -z "$branches_to_delete" ]; then
    echo "No local branches with missing upstreams to remove."
    exit 0
fi

echo "The following local branches have upstreams that no longer exist and will be deleted:"
echo "$branches_to_delete"
echo
read -p "Are you sure you want to delete these branches? [y/N]: " confirm
if [[ "$confirm" =~ ^[Yy]$ ]]; then
    for branch in $branches_to_delete; do
        git branch -D "$branch"
    done
    echo "Stale local branches removed."
else
    echo "Aborted. No branches were deleted."
fi
