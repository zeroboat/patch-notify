from .models import Solution

def sidebar_menu(request):
    solutions = Solution.objects.prefetch_related('products').all()
    
    return {
        'side_solutions': solutions
    }