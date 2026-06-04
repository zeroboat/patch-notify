from .models import Solution, Utility

def sidebar_menu(request):
    solutions = Solution.objects.filter(
        solution_type=Solution.TYPE_PRODUCT
    ).prefetch_related('products').order_by('order', 'id')

    utilities = Utility.objects.order_by('platform', 'order', 'name')

    platform_map = {}
    for u in utilities:
        platform_map.setdefault(u.platform, []).append(u)

    side_utility_platforms = [
        {'key': key, 'label': label, 'utilities': platform_map.get(key, [])}
        for key, label in Utility.PLATFORM_CHOICES
        if key in platform_map
    ]

    return {
        'side_solutions': solutions,
        'side_utility_platforms': side_utility_platforms,
    }