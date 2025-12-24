#!/bin/bash
# Fix Migration Heads Script
# Automatically detects and merges multiple migration heads

set -e  # Exit on error

echo "🔍 Checking migration heads..."
echo ""

# Get heads and count them
heads_output=$(SERVER_NAME=localhost CACHE_TYPE=NullCache uv run flask db heads 2>/dev/null | grep "(head)")
head_count=$(echo "$heads_output" | grep -c "(head)" || true)

if [ "$head_count" -eq 1 ]; then
    echo "✅ Single migration head found - no action needed"
    echo ""
    echo "Current head:"
    echo "$heads_output"
    exit 0
elif [ "$head_count" -eq 0 ]; then
    echo "❌ No migration heads found!"
    echo "This might indicate:"
    echo "  - No migrations exist yet"
    echo "  - Database connection issues"
    echo "  - Migration files are missing"
    exit 1
else
    echo "⚠️  Multiple heads detected ($head_count heads):"
    echo ""
    echo "$heads_output"
    echo ""

    # Extract revision IDs (up to 4 heads supported)
    heads_array=()
    while IFS= read -r line; do
        if [ -n "$line" ]; then
            revision=$(echo "$line" | awk '{print $1}')
            heads_array+=("$revision")
        fi
    done <<< "$heads_output"

    echo "Found revisions: ${heads_array[@]}"
    echo ""

    # Ask for confirmation
    read -p "Create merge migration for these heads? (y/n): " -n 1 -r
    echo ""

    if [[ $REPLY =~ ^[Yy]$ ]]; then
        # Generate merge message
        timestamp=$(date +"%Y%m%d")
        merge_msg="merge migration heads $timestamp"

        echo "Creating merge migration..."

        # Create merge migration (supports 2-4 heads)
        if [ ${#heads_array[@]} -eq 2 ]; then
            SERVER_NAME=localhost CACHE_TYPE=NullCache uv run flask db merge ${heads_array[0]} ${heads_array[1]} -m "$merge_msg"
        elif [ ${#heads_array[@]} -eq 3 ]; then
            SERVER_NAME=localhost CACHE_TYPE=NullCache uv run flask db merge ${heads_array[0]} ${heads_array[1]} ${heads_array[2]} -m "$merge_msg"
        elif [ ${#heads_array[@]} -eq 4 ]; then
            SERVER_NAME=localhost CACHE_TYPE=NullCache uv run flask db merge ${heads_array[0]} ${heads_array[1]} ${heads_array[2]} ${heads_array[3]} -m "$merge_msg"
        else
            echo "❌ Unsupported number of heads: ${#heads_array[@]}"
            echo "Manual intervention required"
            exit 1
        fi

        echo ""
        echo "✅ Merge migration created successfully!"
        echo ""
        echo "Next steps:"
        echo "1. Review the generated migration file in migrations/versions/"
        echo "2. Test the migration: SERVER_NAME=localhost CACHE_TYPE=NullCache uv run flask db upgrade"
        echo "3. Commit the migration:"
        echo "   git add migrations/"
        echo "   git commit -m 'Merge migration heads after upstream sync'"
        echo "4. Run ./check-pr.sh to verify everything is ready"
    else
        echo "Cancelled - no changes made"
        exit 1
    fi
fi
