import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import confusion_matrix, classification_report, roc_curve, auc

class ResultsAnalyzer:
    def __init__(self, model_results, true_values=None):
        self.results = model_results
        self.true_values = true_values
        
    def plot_distribution(self):
        fig, axes = plt.subplots(2, 3, figsize=(15, 10))
        properties = ['absorption', 'distribution', 'metabolism', 
                     'excretion', 'toxicity']
        
        for ax, prop in zip(axes.flat, properties):
            if prop in self.results:
                sns.histplot(self.results[prop], ax=ax)
                ax.set_title(f'{prop.capitalize()} Distribution')
        
        plt.tight_layout()
        return fig