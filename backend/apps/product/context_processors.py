from .models import Solution, Utility

def sidebar_menu(request):
    solutions = Solution.objects.filter(
        solution_type=Solution.TYPE_PRODUCT
    ).prefetch_related('products').order_by('order', 'id')

    side_utilities = Utility.objects.order_by('platform', 'order', 'name')

    return {
        'side_solutions': solutions,
        'side_utilities': side_utilities,
    }