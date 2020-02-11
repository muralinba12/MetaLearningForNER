import coloredlogs
import logging
import os
import torch
import numpy as np
from torch.utils.tensorboard import SummaryWriter

from models.seq_proto import SeqPrototypicalNetwork

logger = logging.getLogger('ProtoLearningLog')
coloredlogs.install(logger=logger, level='DEBUG',
                    fmt='%(asctime)s - %(name)s - %(levelname)s'
                        ' - %(message)s')
tensorboard_writer = SummaryWriter(log_dir='runs/ProtoNet')


class PrototypicalNetwork:
    def __init__(self, config):
        self.base_path = config['base_path']
        self.stamp = config['stamp']
        self.updates = config['num_updates']
        self.meta_epochs = config['num_meta_epochs']
        self.early_stopping = config['early_stopping']
        self.stopping_threshold = config.get('stopping_threshold', 1e-3)

        if 'seq_meta' in config['meta_model']:
            self.proto_model = SeqPrototypicalNetwork(config)

        logger.info('Prototypical network instantiated')

    def training(self, train_episodes):
        best_loss = float('inf')
        best_f1 = 0
        patience = 0
        model_path = os.path.join(self.base_path, 'saved_models', 'ProtoNet-{}.h5'.format(self.stamp))
        logger.info('Model name: ProtoNet-{}.h5'.format(self.stamp))
        for epoch in range(self.meta_epochs):
            losses, accuracies, precisions, recalls, f1s = self.proto_model(train_episodes, self.updates)
            avg_loss = np.mean(losses)
            avg_accuracy = np.mean(accuracies)
            avg_precision = np.mean(precisions)
            avg_recall = np.mean(recalls)
            avg_f1 = np.mean(f1s)

            logger.info('Meta epoch {}: Avg loss = {:.5f}, avg accuracy = {:.5f}, avg precision = {:.5f}, '
                        'avg recall = {:.5f}, avg F1 score = {:.5f}'.format(epoch + 1, avg_loss, avg_accuracy,
                                                                            avg_precision, avg_recall, avg_f1))

            if avg_loss < best_loss - self.stopping_threshold:
                patience = 0
                best_loss = avg_loss
                best_f1 = avg_f1
                torch.save(self.proto_model.learner.state_dict(), model_path)
                logger.info('Saving the model since the loss improved')
                logger.info('')
            else:
                patience += 1
                logger.info('Loss did not improve')
                logger.info('')
                if patience == self.early_stopping:
                    break

            # Log training data into tensorboard
            tensorboard_writer.add_scalar('Loss/train', avg_loss, global_step=epoch + 1)
            for name, param in self.meta_model.named_parameters():
                if param.requires_grad and param.grad is not None:
                    tensorboard_writer.add_histogram('Params/' + name, param.data.view(-1),
                                                     global_step=epoch + 1)
                    tensorboard_writer.add_histogram('Grads/' + name, param.grad.data.view(-1),
                                                     global_step=epoch + 1)

        self.proto_model.learner.load_state_dict(torch.load(model_path))
        return best_f1

    def testing(self, test_episodes):
        logger.info('---------- Proto testing starts here ----------')
        episode_accuracies, episode_precisions, episode_recalls, episodes_f1s = [], [], [], []
        for episode in test_episodes:
            _, accuracy, precision, recall, f1_score = self.proto_model([episode], updates=1, testing=True)
            accuracy, precision, recall, f1_score = accuracy[0], precision[0], recall[0], f1_score[0]

        episode_accuracies.append(accuracy)
        episode_precisions.append(precision)
        episode_recalls.append(recall)
        episodes_f1s.append(f1_score)

        logger.info('Avg meta-testing metrics: Accuracy = {:.5f}, precision = {:.5f}, recall = {:.5f}, '
                    'F1 score = {:.5f}'.format(np.mean(episode_accuracies),
                                               np.mean(episode_precisions),
                                               np.mean(episode_recalls),
                                               np.mean(episodes_f1s)))
